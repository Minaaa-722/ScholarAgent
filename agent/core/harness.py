import json
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from agent.core.state import AgentState, StateMachine
from agent.core.llm import LLMBase
from agent.feedback.base import ValidationResult
from agent.feedback.aggregator import FeedbackAggregator
from agent.feedback.repair_generator import RepairGenerator
from agent.feedback.check_citations import CitationChecker
from agent.feedback.check_coherence import CoherenceChecker
from agent.feedback.check_word_count import WordCountChecker
from agent.feedback.detect_hallucination import HallucinationDetector
from agent.feedback.polish_language import LanguagePolisher
from agent.tools.retrieval import ArxivSearch, SemanticScholarSearch, MergeResults
from agent.tools.processing import SortByCitation, FormatBibtex

logger = logging.getLogger(__name__)

# Progress callback type: (stage: str, message: str, detail: dict | None)
ProgressCallback = Callable[[str, str, Optional[dict]], None]


@dataclass
class HarnessConfig:
    max_papers: int = 20
    max_retries: int = 3
    quality_threshold: float = 0.7
    year_start: int = 2020
    year_end: int = 2026


@dataclass
class TaskInfo:
    topic: str
    keywords: list[str] = field(default_factory=list)
    goal: str = ""
    max_papers: int = 20


# ---------------------------------------------------------------------------
# Tool definitions exposed to the LLM for function calling
# ---------------------------------------------------------------------------
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "arxiv_search",
            "description": "Search arXiv for papers matching a query",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Maximum results (max 100)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_scholar_search",
            "description": "Search Semantic Scholar for peer-reviewed papers with citation data",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Maximum results (max 100)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sort_by_citation",
            "description": "Sort papers by citation count descending",
            "parameters": {
                "type": "object",
                "properties": {
                    "papers": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["papers"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "format_bibtex",
            "description": "Generate BibTeX citation for a paper",
            "parameters": {
                "type": "object",
                "properties": {
                    "paper": {"type": "object"},
                },
                "required": ["paper"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Harness — core pipeline orchestrator
# ---------------------------------------------------------------------------
class Harness:
    def __init__(self, config: HarnessConfig, llm: LLMBase):
        self.config = config
        self.llm = llm
        self.state = StateMachine()
        self.task: Optional[TaskInfo] = None
        self.retry_count: int = 0
        self.has_warnings: bool = False
        self._aggregator = FeedbackAggregator(pass_threshold=config.quality_threshold)
        self._repair_generator = RepairGenerator()
        self._validators = [
            CitationChecker(),
            CoherenceChecker(),
            WordCountChecker(min_words=200, max_words=8000),
            HallucinationDetector(),
            LanguagePolisher(),
        ]
        self._arxiv_search = ArxivSearch()
        self._semantic_scholar = SemanticScholarSearch()
        self._merge = MergeResults()
        self._sort = SortByCitation()
        self._bibtex = FormatBibtex()
        # Execution log for debugging
        self.execution_log: list[dict] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def start(self, topic: str, keywords: str = "", goal: str = "") -> None:
        self.task = TaskInfo(
            topic=topic,
            keywords=[k.strip() for k in keywords.split(",") if k.strip()],
            goal=goal,
            max_papers=self.config.max_papers,
        )
        self.retry_count = 0
        self.has_warnings = False
        self.execution_log = []
        self.state.transition_to(AgentState.PLANNING)

    def get_task_info(self) -> dict:
        if not self.task:
            return {"status": self.state.current_state.name}
        return {
            "topic": self.task.topic,
            "keywords": self.task.keywords,
            "goal": self.task.goal,
            "max_papers": self.task.max_papers,
            "status": self.state.current_state.name,
            "retry_count": self.retry_count,
            "has_warnings": self.has_warnings,
        }

    def inject_feedback(self, results: list[ValidationResult]) -> None:
        report = self._aggregator.aggregate(results)
        if report.overall_passed:
            self.state.transition_to(AgentState.COMPLETE)
            return
        if self.retry_count >= self.config.max_retries:
            self.has_warnings = True
            self.state.transition_to(AgentState.COMPLETE)
            return
        self.retry_count += 1
        self.state.transition_to(AgentState.WRITING)

    def interrupt(self) -> None:
        self.state.interrupt()

    def resume(self) -> None:
        self.state.resume()

    # ------------------------------------------------------------------
    # Full pipeline run
    # ------------------------------------------------------------------
    def run(
        self,
        topic: str,
        keywords: str = "",
        goal: str = "",
        on_progress: Optional[ProgressCallback] = None,
    ) -> dict:
        """Run the full survey-generation pipeline end-to-end.

        Returns a result dict with keys:
          - status: "complete" | "complete_with_warnings" | "error"
          - paper: full survey text (CVPR format)
          - execution_log: list of stage records
          - rounds: number of writing-validation rounds
          - error: error message if status is "error"
        """
        self.start(topic, keywords, goal)

        try:
            return self._pipeline(on_progress)
        except Exception as e:
            logger.exception("Pipeline failed with fatal error")
            self._safe_transition(AgentState.ERROR)
            self._log("ERROR", {"error": str(e)})
            return {
                "status": "error",
                "error": str(e),
                "execution_log": self.execution_log,
            }

    # ------------------------------------------------------------------
    # Pipeline stages (private)
    # ------------------------------------------------------------------
    def _pipeline(self, on_progress: Optional[ProgressCallback]) -> dict:
        """Internal pipeline orchestration."""
        # ---- Stage 1: PLANNING ----
        self._progress(on_progress, "planning", "Generating research plan…")
        plan = self._generate_plan()
        self._log("PLANNING", {"plan": plan[:300] if plan else ""})
        self.state.transition_to(AgentState.RETRIEVAL)

        # ---- Stage 2: RETRIEVAL ----
        self._progress(on_progress, "retrieval", "Searching arXiv and Semantic Scholar…")
        papers = self._retrieve_papers(plan)
        self._log("RETRIEVAL", {"paper_count": len(papers)})
        self.state.transition_to(AgentState.ANALYSIS)

        # ---- Stage 3: ANALYSIS ----
        self._progress(on_progress, "analysis", "Analyzing retrieved papers…")
        analysis = self._analyze_papers(papers, plan)
        self._log("ANALYSIS", {"analysis_summary": (analysis or "")[:300]})
        self.state.transition_to(AgentState.WRITING)

        # ---- Stage 4-6: WRITING + VALIDATION loop ----
        rounds = 0
        final_draft = ""
        while rounds <= self.config.max_retries:
            # 4. WRITING
            self._progress(
                on_progress, "writing",
                f"Writing survey draft (round {rounds + 1})…",
            )
            draft = self._write_survey(analysis, plan, papers, rounds)
            final_draft = draft
            self._log("WRITING", {"round": rounds, "length": len(draft)})
            self.state.transition_to(AgentState.VALIDATION)

            # 5. VALIDATION
            self._progress(on_progress, "validation", "Running 5-dimension quality validation…")
            results = self._run_validators(draft)
            report = self._aggregator.aggregate(results)
            self._log("VALIDATION", {
                "round": rounds,
                "score": round(report.overall_score, 3),
                "passed": report.overall_passed,
                "failures": report.failed_validators,
            })

            if report.overall_passed:
                self.state.transition_to(AgentState.COMPLETE)
                self._progress(on_progress, "complete", "All quality checks passed!")
                return self._result(final_draft, "complete", rounds)

            # 6. FEEDBACK / repair
            repairs = self._repair_generator.generate(results)
            self._log("FEEDBACK", {"round": rounds, "repairs": repairs})

            if rounds >= self.config.max_retries:
                self.has_warnings = True
                self.state.transition_to(AgentState.COMPLETE)
                self._progress(
                    on_progress, "complete",
                    f"Max retries ({self.config.max_retries}) reached. Completing with warnings.",
                )
                return self._result(final_draft, "complete_with_warnings", rounds)

            # Prepare for next iteration
            self.retry_count += 1
            rounds += 1
            self.state.transition_to(AgentState.WRITING)

            # Regenerate analysis with repair context
            analysis = self._incorporate_feedback(analysis, repairs, plan)

        # Should not reach here
        self.has_warnings = True
        self._safe_transition(AgentState.COMPLETE)
        return self._result(final_draft, "complete_with_warnings", rounds)

    # ------------------------------------------------------------------
    # LLM-powered stage helpers
    # ------------------------------------------------------------------
    def _generate_plan(self) -> str:
        """Use LLM to create a structured research plan."""
        topic = self.task.topic
        keywords = ", ".join(self.task.keywords) if self.task.keywords else "none specified"
        goal = self.task.goal or "Write a comprehensive CVPR-format survey paper"

        sys_prompt = (
            "You are a research planning assistant specializing in computer vision and machine learning. "
            "Create a detailed survey paper outline. "
            "Include: introduction, background, taxonomy of approaches, key methods comparison table, "
            "future directions, and conclusion. "
            "For each section, list 3-5 bullet points of what to cover."
        )
        user_msg = (
            f"Topic: {topic}\n"
            f"Keywords: {keywords}\n"
            f"Goal: {goal}\n\n"
            f"Please produce a structured outline for a CVPR-format survey paper. "
            f"Focus on the years {self.config.year_start}–{self.config.year_end}."
        )

        resp = self._safe_llm_call(sys_prompt, user_msg)
        return resp.text

    def _retrieve_papers(self, plan: str) -> list[dict]:
        """Search arXiv and Semantic Scholar, merge and dedup results."""
        topic = self.task.topic
        keywords = self.task.keywords or [topic]

        # Generate search queries via LLM, with robust parsing
        sys_prompt = (
            "You are a literature search assistant. "
            "Generate exactly 3 concise search queries to find papers for a survey. "
            "Return ONLY the 3 queries, one per line, no numbering, no explanation."
        )
        user_msg = f"Survey topic: {topic}\nKeywords: {', '.join(keywords)}\n\nGenerate 3 search queries."
        resp = self._safe_llm_call(sys_prompt, user_msg, use_tools=True)

        # Parse queries: strip any conversational text, keep only plausible search terms
        raw_lines = resp.text.strip().split("\n")
        queries = []
        for line in raw_lines:
            line = line.strip().strip('"').strip("'").strip("-").strip()
            # Skip lines that look like conversational text (too long, start with common phrases)
            if (line
                and len(line) < 200
                and not line.lower().startswith(("here", "sure", "ok", "i'll", "let", "the", "for", "of course"))
                and not line.startswith(("1.", "2.", "3.", "-", "*"))
            ):
                queries.append(line)

        # Fallback: use topic and keyword combinations
        if len(queries) < 1:
            queries = [topic]
        if len(queries) < 2:
            queries.append(f"{topic} survey")
        if len(queries) < 3:
            queries.append(f"{' '.join(keywords[:3])}")

        # Search both sources
        all_results = []
        for q in queries:
            arxiv_res = self._arxiv_search.execute({
                "query": q, "max_results": self.config.max_papers,
            })
            if arxiv_res.success:
                all_results.append(arxiv_res.data)

            ss_res = self._semantic_scholar.execute({
                "query": q, "max_results": self.config.max_papers,
            })
            if ss_res.success:
                all_results.append(ss_res.data)

            time.sleep(0.3)  # Be polite to APIs

        # Merge and dedup
        merged = self._merge.execute({"results": all_results})
        papers = merged.data.get("papers", []) if merged.success else []

        # Sort by citation count
        sorted_res = self._sort.execute({"papers": papers})
        papers = sorted_res.data.get("papers", papers) if sorted_res.success else papers

        return papers[:self.config.max_papers]

    def _analyze_papers(self, papers: list[dict], plan: str) -> str:
        """Use LLM to analyze the retrieved papers."""
        topic = self.task.topic
        keywords = self.task.keywords or [topic]

        if not papers:
            # No papers retrieved — generate analysis from topic knowledge
            sys_prompt = (
                "You are a research analysis assistant. "
                "Provide a detailed technical analysis of the state of the art "
                f"in {topic}. Cover: key approaches, technical challenges, "
                "benchmark datasets, and future directions. "
                "Be specific and cite relevant known works."
            )
            user_msg = (
                f"Survey topic: {topic}\n"
                f"Keywords: {', '.join(keywords)}\n\n"
                f"Research plan:\n{plan[:2000]}\n\n"
                "No papers were retrieved from external sources. "
                "Please provide a comprehensive analysis based on your knowledge "
                "of the field, including specific model names, techniques, and results."
            )
            resp = self._safe_llm_call(sys_prompt, user_msg)
            return resp.text

        # Summarize papers for the LLM (truncate abstracts to avoid token overflow)
        paper_summaries = []
        for i, p in enumerate(papers, 1):
            abstract = (p.get("abstract") or "")[:500]
            authors = ", ".join(p.get("authors", [])[:3])
            paper_summaries.append(
                f"[{i}] {p.get('title', '')}\n"
                f"    Authors: {authors}\n"
                f"    Year: {p.get('year', '')} | Citations: {p.get('citation_count', 0)}\n"
                f"    Abstract: {abstract}\n"
            )
        papers_text = "\n".join(paper_summaries)

        sys_prompt = (
            "You are a research analysis assistant. "
            "Analyze the following papers and extract: "
            "1) Key contributions and innovations\n"
            "2) Common taxonomies / categories\n"
            "3) Main technical approaches compared\n"
            "4) Benchmark datasets and metrics used\n"
            "5) Open challenges and future directions\n\n"
            "Be concise and specific. If some papers are not directly relevant, "
            "focus on the relevant ones and note the others as peripheral."
        )
        user_msg = (
            f"Survey topic: {topic}\n\n"
            f"Research plan:\n{plan[:2000]}\n\n"
            f"Retrieved papers ({len(papers)} total):\n{papers_text[:15000]}"
        )

        resp = self._safe_llm_call(sys_prompt, user_msg)
        return resp.text

    def _write_survey(self, analysis: str, plan: str, papers: list[dict], round_num: int) -> str:
        """Use LLM to write the survey paper in CVPR format."""
        topic = self.task.topic
        keywords = ", ".join(self.task.keywords) if self.task.keywords else topic

        # Build a reference list in CVPR format
        refs = []
        for i, p in enumerate(papers, 1):
            authors = p.get("authors", [])[:3]
            author_str = ", ".join(authors) if authors else "Unknown"
            if len(p.get("authors", [])) > 3:
                author_str += " et al."
            year = p.get("year", 2024)
            title = p.get("title", "Untitled")
            refs.append(f"[{i}] {author_str}. \"{title}.\" {year}.")

        ref_text = "\n".join(refs)

        # If analysis is empty or too short, build a strong topic-based prompt
        if not analysis or len(analysis) < 200:
            analysis_replacement = (
                f"The survey covers the topic of {topic}. "
                f"Key areas include: efficient transformer architectures, "
                f"model compression, quantization, pruning, knowledge distillation, "
                f"hardware-aware design, and edge deployment. "
                f"Discuss recent advances and open challenges."
            )
            analysis = analysis_replacement

        writing_instruction = (
            "Write a comprehensive CVPR-format survey paper on the given topic. "
            "The paper MUST be substantive: each section should have 3-5 detailed paragraphs. "
            "Use \\cite{ref} for citations. "
            "Structure: \\section{Abstract}, \\section{Introduction}, "
            "\\section{Background}, \\section{Taxonomy of Methods}, "
            "\\section{Comparative Analysis}, \\section{Future Directions}, "
            "\\section{Conclusion}."
        )

        sys_prompt = (
            "You are an academic writing assistant specializing in computer vision surveys. "
            f"{writing_instruction}"
        )
        user_msg = (
            f"Title: A Comprehensive Survey on {topic}\n"
            f"Keywords: {keywords}\n\n"
            f"Research Plan:\n{plan[:3000]}\n\n"
            f"Paper Analysis:\n{analysis[:6000]}\n\n"
            f"References:\n{ref_text}\n\n"
            f"Round {round_num + 1} of up to {self.config.max_retries + 1}.\n\n"
            "IMPORTANT: Write the COMPLETE survey paper with all sections. "
            "Each section must have substantive technical content. "
            "Do not leave any section empty or as a placeholder."
        )

        resp = self._safe_llm_call(sys_prompt, user_msg)
        return resp.text

    def _incorporate_feedback(self, analysis: str, repairs: str, plan: str) -> str:
        """Use LLM to revise the analysis based on validation feedback."""
        if not repairs:
            return analysis

        sys_prompt = (
            "You are a research revision assistant. "
            "Revise the paper analysis to address the following quality issues. "
            "Keep the original structure but improve the flagged aspects."
        )
        user_msg = (
            f"Original plan:\n{plan[:1000]}\n\n"
            f"Current analysis:\n{analysis[:4000]}\n\n"
            f"Issues to fix:\n{repairs}\n\n"
            "Provide an improved analysis that addresses all issues."
        )

        resp = self._safe_llm_call(sys_prompt, user_msg)
        return resp.text

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _run_validators(self, draft: str) -> list[ValidationResult]:
        """Run all 5 validators on the draft."""
        # Extract paper IDs from both \cite{ref} and [@paper_id] formats
        paper_ids = []
        import re
        for match in re.finditer(r'\\cite\{([^}]+)\}', draft):
            for ref in match.group(1).split(","):
                paper_ids.append(ref.strip())
        for match in re.finditer(r'\[@(\w+)\]', draft):
            paper_ids.append(match.group(1))

        context = {
            "content": draft or " ",
            "paper_ids": list(set(paper_ids)) if paper_ids else ["ref"],
        }
        return [v.validate(context) for v in self._validators]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _safe_llm_call(self, system_prompt: str, user_message: str, use_tools: bool = False) -> "LLMResponse":
        """Call LLM with optional tool definitions."""
        from agent.core.llm import LLMResponse
        try:
            tools = TOOL_DEFINITIONS if use_tools else None
            return self.llm.generate(system_prompt, user_message, tools=tools)
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            raise RuntimeError(f"LLM call failed: {e}") from e

    def _safe_transition(self, target: AgentState) -> None:
        """Attempt a state transition; log and swallow if invalid."""
        try:
            self.state.transition_to(target)
        except ValueError as e:
            logger.warning("State transition skipped: %s", e)

    def _progress(self, cb: Optional[ProgressCallback], stage: str, msg: str) -> None:
        """Dispatch progress callback if set."""
        if cb:
            cb(stage, msg, self.get_task_info())

    def _log(self, stage: str, data: dict) -> None:
        """Append to execution log with timestamp."""
        self.execution_log.append({
            "stage": stage,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **data,
        })

    def _result(self, paper: str, status: str, rounds: int) -> dict:
        """Build the final result dict."""
        return {
            "status": status,
            "paper": paper,
            "rounds": rounds,
            "retry_count": self.retry_count,
            "has_warnings": self.has_warnings,
            "task": self.get_task_info(),
            "execution_log": self.execution_log,
        }