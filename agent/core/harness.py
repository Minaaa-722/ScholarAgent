import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from agent.core.state import AgentState, StateMachine
from agent.core.llm import LLMBase
from agent.core.pipeline import PipelineOrchestrator, PipelineResult
from agent.feedback.base import ValidationResult
from agent.feedback.aggregator import FeedbackAggregator
from agent.feedback.repair_generator import RepairGenerator
from agent.feedback.check_citations import CitationChecker
from agent.feedback.check_coherence import CoherenceChecker
from agent.feedback.check_word_count import WordCountChecker
from agent.feedback.detect_hallucination import HallucinationDetector
from agent.feedback.polish_language import LanguagePolisher
from agent.feedback.latex_repair import LatexFormatRepair
from agent.tools.retrieval import ArxivSearch, SemanticScholarSearch, MergeResults
from agent.tools.processing import SortByCitation, FormatBibtex, PdfDownload, PdfParse, Dedup
from agent.tools.auxiliary import WebSearch, ShellExec
from agent.tools.registry import ToolRegistry
from agent.guardrails.manager import GuardrailManager
from agent.memory.integration import MemoryIntegration

logger = logging.getLogger(__name__)

# Progress callback type: (stage: str, message: str, detail: dict | None)
ProgressCallback = Callable[[str, str, Optional[dict]], None]


@dataclass
class HarnessConfig:
    max_papers: int = 20
    max_retries: int = 3
    quality_threshold: float = 0.7
    max_pipeline_retries: int = 2  # Per-phase retries for transient errors (2 = 3 total attempts)
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
        self._pipeline_running: bool = False
        self.current_stage: str = ""
        self.current_message: str = ""
        self._aggregator = FeedbackAggregator(pass_threshold=config.quality_threshold)
        self._repair_generator = RepairGenerator()
        self._validators = [
            CitationChecker(),
            CoherenceChecker(),
            WordCountChecker(min_words=200, max_words=8000),
            HallucinationDetector(),
            LanguagePolisher(),
        ]
        # Legacy tool instances (kept for backward compatibility)
        self._arxiv_search = ArxivSearch()
        self._semantic_scholar = SemanticScholarSearch()
        self._merge = MergeResults()
        self._sort = SortByCitation()
        self._bibtex = FormatBibtex()
        # Execution log for debugging
        self.execution_log: list[dict] = []
        self.last_result: Optional[dict] = None
        self.task_started_at: str = ""
        self.latex_repair_log = None
        # 错误恢复状态
        self._pipeline_retry_count: int = 0
        self._last_failed_stage: Optional[AgentState] = None
        self._error_message: str = ""
        # 反馈队列（线程安全）
        self.feedback_queue: list[dict] = []
        self.feedback_history: list[dict] = []
        self._feedback_lock = threading.Lock()
        # 阶段执行产物（用于前端展示）
        self._plan: str = ""
        self._papers: list[dict] = []
        self._analysis: str = ""
        self._draft_sections: list[dict] = []
        self._validation_scores: dict = {}
        self._retrieved_queries: list[str] = []
        self._pending_expansions: list[str] = []
        self._pending_revisions: list[str] = []

        # ---- New: ToolRegistry, Guardrails, Memory, Orchestrator ----
        # ToolRegistry — register all tools
        self._tool_registry = ToolRegistry()
        self._tool_registry.register(self._arxiv_search)
        self._tool_registry.register(self._semantic_scholar)
        self._tool_registry.register(self._merge)
        self._tool_registry.register(self._sort)
        self._tool_registry.register(self._bibtex)
        self._tool_registry.register(PdfDownload())
        self._tool_registry.register(PdfParse())
        self._tool_registry.register(Dedup())
        self._tool_registry.register(WebSearch())
        self._tool_registry.register(ShellExec())

        # Guardrails
        self._guardrail_manager = GuardrailManager()

        # Memory integration
        self._memory_integration = MemoryIntegration()

        # Interrupt event (shared between Harness and PipelineOrchestrator)
        self._interrupt_event = threading.Event()

        # PipelineOrchestrator — the new pipeline engine
        self._orchestrator = PipelineOrchestrator(
            llm=llm,
            tools=self._tool_registry,
            validators=self._validators,
            guardrails=self._guardrail_manager,
            config=config,
            latex_repair=LatexFormatRepair(),
        )
        self._orchestrator.set_interrupt_event(self._interrupt_event)

        # Add EvidenceChecker to the validator list (uses the orchestrator's stores)
        from agent.evidence.checker import EvidenceChecker
        self._validators.append(
            EvidenceChecker(
                evidence_store=self._orchestrator._evidence_store,
                benchmark_store=self._orchestrator._benchmark_store,
                knowledge_base=self._orchestrator._paper_knowledge_base,
                llm=llm,
            )
        )

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
        self._pipeline_retry_count = 0
        self._last_failed_stage = None
        self._error_message = ""
        self.execution_log = []
        self.last_result = None
        self.task_started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        # 重置反馈队列和阶段产物
        self.feedback_queue = []
        self.feedback_history = []
        self._plan = ""
        self._papers = []
        self._analysis = ""
        self._draft_sections = []
        self._validation_scores = {}
        self._retrieved_queries = []
        self._pending_expansions = []
        self._pending_revisions = []
        # Reset orchestrator state too
        self._orchestrator.execution_log = []
        self._orchestrator._pipeline_retry_count = 0
        self._orchestrator._last_failed_stage = None
        self._orchestrator._error_message = ""
        self._orchestrator._plan = ""
        self._orchestrator._papers = []
        self._orchestrator._analysis = ""
        self._orchestrator._draft_sections = []
        self._orchestrator._validation_scores = {}
        self._orchestrator._retrieved_queries = []
        self._orchestrator._pending_expansions = []
        self._orchestrator._pending_revisions = []
        self._orchestrator.latex_repair_log = None
        # Reset state machine if in terminal state (e.g. COMPLETE from previous run)
        if self.state.is_terminal():
            self.state = StateMachine()
        self.state.transition_to(AgentState.PLANNING)

    def get_task_info(self) -> dict:
        details = {}
        if self._plan:
            lines = [l.strip() for l in self._plan.split("\n") if l.strip()]
            preview_lines = [l for l in lines if len(l) > 10][:5]
            details["plan"] = {
                "summary": "Research plan generated",
                "preview": preview_lines,
                "section_count": sum(1 for l in lines if l.startswith(("\\section", "- **", "###"))),
            }
        if self._papers:
            paper_list = []
            for p in self._papers:
                authors = p.get("authors", [])[:3]
                author_str = ", ".join(authors) if authors else "Unknown"
                if len(p.get("authors", [])) > 3:
                    author_str += " et al."
                paper_list.append({
                    "title": p.get("title", "Untitled"),
                    "authors": author_str,
                    "year": p.get("year", ""),
                    "citations": p.get("citation_count", 0),
                    "source": "arxiv" if p.get("arxiv_id") else "semantic_scholar",
                    "url": p.get("url", ""),
                })
            details["papers"] = {
                "total": len(self._papers),
                "list": paper_list,
            }
        if self._retrieved_queries:
            details["search_queries"] = self._retrieved_queries
        if self._analysis:
            details["analysis"] = {
                "summary": "Paper analysis completed",
                "preview": self._analysis,
            }
        if self._draft_sections:
            details["sections"] = self._draft_sections
        if self._validation_scores:
            details["validation"] = self._validation_scores

        if not self.task:
            return {
                "status": self.state.current_state.name,
                "pipeline_running": self._pipeline_running,
                "error": self._error_message,
                "pipeline_retry_count": self._pipeline_retry_count,
                "last_failed_stage": self._last_failed_stage.name if self._last_failed_stage else "",
                "execution_details": details,
                "feedback_queue": self.feedback_queue,
                "feedback_history": self.feedback_history,
            }
        return {
            "topic": self.task.topic,
            "keywords": self.task.keywords,
            "goal": self.task.goal,
            "max_papers": self.task.max_papers,
            "status": self.state.current_state.name,
            "pipeline_running": self._pipeline_running,
            "current_stage": self.current_stage,
            "current_message": self.current_message,
            "retry_count": self.retry_count,
            "has_warnings": self.has_warnings,
            "task_started_at": self.task_started_at,
            "error": self._error_message,
            "pipeline_retry_count": self._pipeline_retry_count,
            "last_failed_stage": self._last_failed_stage.name if self._last_failed_stage else "",
            "execution_details": details,
            "feedback_queue": self.feedback_queue,
            "feedback_history": self.feedback_history,
        }

    def get_paper(self) -> dict:
        """Return the final pipeline result (paper, log, etc.) or empty dict."""
        return self.last_result or {}

    def get_execution_log(self) -> list[dict]:
        """Return the execution log."""
        return self.execution_log

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
        self._interrupt_event.set()

    def resume(self) -> None:
        self.state.resume()
        self._interrupt_event.clear()

    def submit_human_feedback(self, category: str, content: str) -> dict:
        """外部 API 调用此方法注入反馈"""
        import uuid
        feedback = {
            "id": str(uuid.uuid4())[:8],
            "category": category,
            "content": content,
            "status": "pending",
            "received_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        with self._feedback_lock:
            self.feedback_queue.append(feedback)
        return feedback

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
        try:
            self.start(topic, keywords, goal)
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

    def run_async(
        self,
        topic: str,
        keywords: str = "",
        goal: str = "",
        on_progress: Optional[ProgressCallback] = None,
    ) -> None:
        """Run the pipeline in a background thread."""
        self._pipeline_running = True
        self.current_stage = "starting"
        self.current_message = "Starting pipeline…"

        def _target():
            try:
                self.last_result = self.run(topic, keywords, goal, on_progress)
            finally:
                self._pipeline_running = False

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # Pipeline stages (private)
    # ------------------------------------------------------------------
    def _pipeline(self, on_progress: Optional[ProgressCallback]) -> dict:
        """Internal pipeline orchestration — delegates to PipelineOrchestrator.

        The orchestrator handles stage execution, retry logic, validation,
        human feedback, and format repair.  After it returns, we sync its
        state back to the Harness for the API / frontend.
        """
        # Wrapper progress callback that updates Harness state too
        def _orchestrator_progress(stage: str, msg: str, detail: Optional[dict]) -> None:
            self.current_stage = stage
            self.current_message = msg
            # Sync all orchestrator state to the Harness so the WebSocket / HTTP
            # polling endpoints see real-time data for every stage (plan, papers,
            # analysis, sections, validation, queries).
            self._sync_orchestrator_state()
            if on_progress:
                on_progress(stage, msg, detail)

        # Run the pipeline via orchestrator
        result: PipelineResult = self._orchestrator.run_pipeline(
            task=self.task,
            state=self.state,
            feedback_queue=self.feedback_queue,
            feedback_lock=self._feedback_lock,
            feedback_history=self.feedback_history,
            on_progress=_orchestrator_progress,
        )

        # Sync orchestrator state back to Harness
        self._sync_orchestrator_state()

        # Build result dict (matching the old _pipeline return format)
        result_dict = {
            "status": result.status,
            "paper": result.paper,
            "rounds": result.rounds,
            "retry_count": self.retry_count,
            "has_warnings": self.has_warnings,
            "task": self.get_task_info(),
            "execution_log": self.execution_log,
            "papers": self._papers,
        }
        if result.latex_repair_log:
            result_dict["latex_repair_log"] = result.latex_repair_log

        # Save task history via memory integration
        if self.task:
            self._memory_integration.save_task_history(self.task, result_dict)

        return result_dict

    def _sync_orchestrator_state(self) -> None:
        """Copy pipeline state from the orchestrator back to the Harness."""
        self._papers = list(self._orchestrator._papers)
        self._plan = self._orchestrator._plan
        self._analysis = self._orchestrator._analysis
        self._draft_sections = list(self._orchestrator._draft_sections)
        self._validation_scores = dict(self._orchestrator._validation_scores)
        self._retrieved_queries = list(self._orchestrator._retrieved_queries)
        self.execution_log = list(self._orchestrator.execution_log)
        self.latex_repair_log = self._orchestrator.latex_repair_log
        self._pipeline_retry_count = self._orchestrator._pipeline_retry_count
        self._last_failed_stage = self._orchestrator._last_failed_stage
        self._error_message = self._orchestrator._error_message

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
        self._plan = resp.text
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

        self._papers = papers[:self.config.max_papers]
        self._retrieved_queries = queries
        return self._papers

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
            self._analysis = resp.text
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
        self._analysis = resp.text
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

        cvpr_format_instructions = (
            "### CVPR FORMAT REQUIREMENTS (STRICT) ###\n"
            "1. DOCUMENT HEADER: Start with:\n"
            "   \\documentclass[10pt,twocolumn,letterpaper]{article}\n"
            "   \\usepackage{cvpr}\n"
            "   \\usepackage{booktabs,amsmath,amssymb}\n"
            "   Do NOT use \\usepackage{geometry} or adjust margins.\n"
            "2. ABSTRACT: Use \\begin{abstract}...\\end{abstract} environment.\n"
            "   Do NOT use \\section{Abstract}.\n"
            "3. BIBLIOGRAPHY: Use ONLY BibTeX with:\n"
            "   \\bibliographystyle{ieeenat}\n"
            "   \\bibliography{references}\n"
            "   Do NOT write \\begin{thebibliography} manually.\n"
            "4. TABLES: Use CVPR three-line table style:\n"
            "   \\toprule / \\midrule / \\bottomrule from booktabs.\n"
            "   Do NOT use \\hline. Table captions go ABOVE the table.\n"
            "   Use [htbp] float placement for all tables.\n"
            "5. FIGURES: Captions go BELOW the figure.\n"
            "6. CITATIONS: Place citations BEFORE the period, not after.\n"
            "   CORRECT: ... as shown in previous work~\\cite{key}.\n"
            "   WRONG: ... as shown in previous work.~\\cite{key}\n"
            "7. ACRONYMS: Define all acronyms at first use.\n"
            "   Example: Test-Time Adaptation (TTA), Batch Normalization (BN).\n"
            "8. TIME RANGE: Survey covers 2020-2025. Works before 2020 are "
            "foundational prior work. Use 2025, not 2026.\n"
            "9. FAST INFERENCE: If discussing pruning, quantization, dynamic "
            "early exit, or NAS in the Quick Test / inference context, include "
            "this sentence: 'These optimizations reduce runtime latency during "
            "inference, hence belong to the test-phase pipeline.'\n"
            "10. TYPOGRAPHY: Use --- for em-dash, -- for en-dash. "
            "Use `` and '' for quotes, not Unicode smart quotes.\n"
            "11. PAGE LIMIT: CVPR main body is 8 pages max. "
            "Bibliography does not count toward page limit.\n"
            "12. Use \\section* for the abstract heading if needed, but prefer "
            "the \\begin{abstract} environment.\n"
            "13. All \\cite{} keys must use BibTeX-style keys (e.g., author2023title).\n"
            "### END CVPR FORMAT REQUIREMENTS ###\n"
        )

        sys_prompt = (
            "You are an academic writing assistant specializing in computer vision surveys. "
            f"{writing_instruction}\n\n{cvpr_format_instructions}"
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
        self._draft_sections = self._extract_sections(resp.text)
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
        results = [v.validate(context) for v in self._validators]
        self._validation_scores = {
            r.validator_name: {
                "score": r.score,
                "passed": r.passed,
                "message": (r.repair_instructions or "")[:200],
            }
            for r in results
        }
        return results

    # ------------------------------------------------------------------
    # Human feedback handling
    # ------------------------------------------------------------------
    def _check_human_feedback(self, on_progress: Optional[ProgressCallback]) -> None:
        """检查并处理待处理的反馈（在阶段边界调用）"""
        with self._feedback_lock:
            if not self.feedback_queue:
                return
            feedback = self.feedback_queue.pop(0)
            feedback["status"] = "processing"
            self.feedback_history.append(feedback)

        short = feedback["content"][:60]
        self._progress(on_progress, "feedback", f"Processing feedback ({feedback['category']}): {short}…")

        if feedback["category"] == "supplement_papers":
            self._progress(on_progress, "retrieval", f"Supplementing papers: {short}…")
            new_papers = self._supplement_retrieval(feedback["content"])
            self._papers.extend(new_papers)
            # Dedup by title
            seen_titles = set()
            deduped = []
            for p in self._papers:
                t = (p.get("title") or "").strip().lower()
                if t and t not in seen_titles:
                    seen_titles.add(t)
                    deduped.append(p)
            self._papers = deduped

            self._progress(on_progress, "analysis", "Re-analyzing with supplemented papers…")
            self._analysis = self._analyze_papers(self._papers, self._plan)

        elif feedback["category"] == "expand_section":
            self._pending_expansions.append(feedback["content"])

        elif feedback["category"] == "general":
            self._pending_revisions.append(feedback["content"])

        feedback["status"] = "applied"
        self._progress(on_progress, "feedback", f"Feedback applied: {short}…")

    def _supplement_retrieval(self, feedback_content: str) -> list[dict]:
        """根据反馈内容进行补充检索"""
        sys_prompt = (
            "You are a literature search assistant. "
            "Extract a concise search query from the user's feedback. "
            "Return ONLY the query, no explanation."
        )
        resp = self._safe_llm_call(sys_prompt, feedback_content)
        query = resp.text.strip().strip('"').strip("'")

        if not query or len(query) > 200:
            query = feedback_content[:100]

        all_results = []
        arxiv_res = self._arxiv_search.execute({"query": query, "max_results": 10})
        if arxiv_res.success:
            all_results.append(arxiv_res.data)

        ss_res = self._semantic_scholar.execute({"query": query, "max_results": 10})
        if ss_res.success:
            all_results.append(ss_res.data)

        time.sleep(0.3)
        merged = self._merge.execute({"results": all_results})
        return merged.data.get("papers", []) if merged.success else []

    # ------------------------------------------------------------------
    # Error recovery helpers
    # ------------------------------------------------------------------
    def _ensure_state(self, target: AgentState) -> None:
        """Transition to target state if not already there."""
        if self.state.current_state != target:
            self._safe_transition(target)

    def _retry_on_error(
        self,
        fn: Callable[[], Any],
        stage: AgentState,
        on_progress: Optional[ProgressCallback],
    ) -> Any:
        """Execute a stage function with phase-level retry.

        Retries up to max_pipeline_retries times on exception, with
        exponential backoff.  Preserves results from completed phases.
        """
        for attempt in range(1, self.config.max_pipeline_retries + 2):
            try:
                self._ensure_state(stage)
                return fn()
            except Exception as e:
                self._pipeline_retry_count = attempt
                self._last_failed_stage = stage
                self._error_message = str(e)
                self._safe_transition(AgentState.ERROR)
                self._log("ERROR", {
                    "stage": stage.name,
                    "error": str(e),
                    "attempt": attempt,
                    "max_attempts": self.config.max_pipeline_retries + 1,
                })

                if attempt <= self.config.max_pipeline_retries:
                    wait = 2 ** attempt  # 2s, 4s
                    logger.warning(
                        "Stage %s failed (attempt %d/%d): %s. Retrying in %ds …",
                        stage.name, attempt, self.config.max_pipeline_retries + 1, e, wait,
                    )
                    self._progress(
                        on_progress, "retrying",
                        f"⚠ {stage.name} failed (attempt {attempt}/"
                        f"{self.config.max_pipeline_retries + 1}): "
                        f"{e!s:.80}. Retrying in {wait}s …",
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "Stage %s failed after %d attempts. Giving up.",
                        stage.name, self.config.max_pipeline_retries + 1,
                    )
                    raise  # All retries exhausted

    def restart(self) -> None:
        """Re-launch the pipeline with the same task parameters from ERROR state."""
        if self.state.current_state != AgentState.ERROR:
            raise ValueError("Can only restart from ERROR state")
        if not self.task:
            raise ValueError("No task to restart")

        # Reset error state
        self._pipeline_retry_count = 0
        self._last_failed_stage = None
        self._error_message = ""
        self._orchestrator.reset_error_state()

        self.run_async(
            topic=self.task.topic,
            keywords=", ".join(self.task.keywords),
            goal=self.task.goal,
        )

    @staticmethod
    def _extract_sections(draft: str) -> list[dict]:
        """从 LaTeX 草稿中提取章节结构"""
        import re
        sections = []
        for match in re.finditer(r'\\(?:sub)*section\{([^}]+)\}', draft):
            sections.append({
                "level": match.group(0).count("sub"),
                "title": match.group(1),
            })
        return sections

    # ------------------------------------------------------------------
    # Format repair (CVPR LaTeX post-processing)
    # ------------------------------------------------------------------
    def _format_repair(self, draft: str) -> str:
        """Run CVPR format repair on the LaTeX draft.

        Applies the 10-rule LatexFormatRepair pipeline to ensure the output
        strictly conforms to CVPR submission format.
        """
        repair = LatexFormatRepair()
        repair_log = repair.repair(draft)
        self.latex_repair_log = repair_log

        if repair_log.has_changes:
            logger.info(
                "CVPR format repair: %d change(s) applied",
                repair_log.change_count,
            )
            for entry in repair_log.entries:
                logger.debug("  %s", entry.short())
        else:
            logger.info("CVPR format repair: no changes needed")

        return repair_log.fixed_text

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
        """Dispatch progress callback if set, and store current progress."""
        self.current_stage = stage
        self.current_message = msg
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
        result = {
            "status": status,
            "paper": paper,
            "rounds": rounds,
            "retry_count": self.retry_count,
            "has_warnings": self.has_warnings,
            "task": self.get_task_info(),
            "execution_log": self.execution_log,
        }
        # Include LaTeX repair log if available
        if self.latex_repair_log is not None:
            result["latex_repair_log"] = {
                "change_count": self.latex_repair_log.change_count,
                "summary": self.latex_repair_log.summary(),
                "entries": [
                    {
                        "rule": e.rule,
                        "location": e.location,
                        "original": e.original,
                        "replacement": e.replacement,
                    }
                    for e in self.latex_repair_log.entries
                ],
            }
        return result