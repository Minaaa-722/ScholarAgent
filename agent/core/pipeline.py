import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from agent.core.state import AgentState, StateMachine
from agent.core.llm import LLMBase, LLMResponse
from agent.evidence.evidence_store import EvidenceStore, ClaimContextBuilder
from agent.evidence.claim_extractor import ClaimExtractor
from agent.evidence.verifier import ClaimVerifier
from agent.evidence.benchmark_store import BenchmarkStore
from agent.evidence.paper_knowledge import PaperKnowledgeBase
from agent.evidence.benchmark_extractor import BenchmarkExtractor
from agent.evidence.paper_analyzer import PaperAnalyzer
from agent.evidence.pdf_parser import PDFParser, PDFChunk
from agent.evidence.evidence_extractor import EvidenceExtractor
from agent.evidence.evidence_reference import EvidenceReference
from agent.evidence.context_retriever import ContextRetriever, EvidenceContextBuilder
from agent.feedback.base import ValidationResult, Validator
from agent.guardrails.manager import GuardrailManager
from agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# Progress callback type: (stage: str, message: str, detail: dict | None)
ProgressCallback = Callable[[str, str, Optional[dict]], None]


@dataclass
class TaskInfo:
    topic: str
    keywords: list[str] = field(default_factory=list)
    goal: str = ""
    max_papers: int = 50


@dataclass
class HarnessConfig:
    max_papers: int = 50
    max_retries: int = 3
    quality_threshold: float = 0.7
    max_pipeline_retries: int = 2
    year_start: int = 2020
    year_end: int = 2026


@dataclass
class PipelineResult:
    paper: str = ""
    status: str = "error"
    rounds: int = 0
    execution_log: list[dict] = field(default_factory=list)
    latex_repair_log: Optional[dict] = None
    validation_scores: dict = field(default_factory=dict)


class PipelineOrchestrator:
    """Orchestrates the survey-generation pipeline stages.

    Owns the stage execution, retry logic, validation loop, human feedback
    checking, and execution logging.  Does not own the public API — that
    remains on Harness.
    """

    def __init__(
        self,
        llm: LLMBase,
        tools: ToolRegistry,
        validators: list[Validator],
        guardrails: GuardrailManager,
        config: HarnessConfig,
        latex_repair: Any,  # LatexFormatRepair
    ):
        self.llm = llm
        self.tools = tools
        self._validators = validators
        self._guardrails = guardrails
        self.config = config
        self._latex_repair = latex_repair

        # Pipeline state (owned by the orchestrator)
        self.execution_log: list[dict] = []
        self._pipeline_retry_count: int = 0
        self._last_failed_stage: Optional[AgentState] = None
        self._error_message: str = ""
        self._plan: str = ""
        self._papers: list[dict] = []
        self._analysis: str = ""
        self._draft_sections: list[dict] = []
        self._validation_scores: dict = {}
        self._retrieved_queries: list[str] = []
        self._pending_expansions: list[str] = []
        self._pending_revisions: list[str] = []
        self.latex_repair_log: Optional[Any] = None

        # Evidence verification
        self._evidence_store = EvidenceStore()
        self._claim_extractor = ClaimExtractor(self.llm)
        self._claim_verifier = ClaimVerifier(self.llm)

        # Evidence grounding layer (Task 6)
        from agent.evidence.benchmark_store import BenchmarkStore
        from agent.evidence.paper_knowledge import PaperKnowledgeBase
        from agent.evidence.benchmark_extractor import BenchmarkExtractor
        from agent.evidence.paper_analyzer import PaperAnalyzer
        from agent.evidence.pdf_parser import PDFParser
        from agent.evidence.evidence_extractor import EvidenceExtractor
        self._benchmark_store = BenchmarkStore()
        self._paper_knowledge_base = PaperKnowledgeBase()
        self._benchmark_extractor = BenchmarkExtractor(self.llm)
        self._paper_analyzer = PaperAnalyzer(self.llm)
        self._pdf_parser = PDFParser()
        self._evidence_extractor = EvidenceExtractor(self.llm)
        from agent.evidence.citation_store import CitationStore
        self._citation_store = CitationStore()
        from agent.evidence.citation_anchor_store import CitationAnchorStore
        self._citation_anchor_store = CitationAnchorStore()
        from agent.evidence.citation_injector import CitationInjector
        self._citation_injector = CitationInjector(self._citation_store)
        from agent.evidence.table_generator import BenchmarkTableGenerator
        self._table_generator = BenchmarkTableGenerator(self._benchmark_store, self._citation_store)
        self._pdf_chunks: dict[str, list[PDFChunk]] = {}
        self._evidence_refs: list[EvidenceReference] = []
        self._evidence_unavailable: set[str] = set()

        # Progress tracking (read by Harness for API responses)
        self.current_stage: str = ""
        self.current_message: str = ""

        # Progress details (consumed by frontend for rich stage display)
        self.stage_messages: list[dict] = []
        self.stage_metrics: dict = {}

        # Interrupt support
        self._interrupt_event: Optional[threading.Event] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_interrupt_event(self, event: threading.Event) -> None:
        """Set the threading.Event used to signal interrupt."""
        self._interrupt_event = event

    def get_error_info(self) -> dict:
        """Return error state info for the Harness facade."""
        return {
            "pipeline_retry_count": self._pipeline_retry_count,
            "last_failed_stage": self._last_failed_stage.name if self._last_failed_stage else "",
            "error": self._error_message,
        }

    def reset_error_state(self) -> None:
        """Reset pipeline error state (called on restart)."""
        self._pipeline_retry_count = 0
        self._last_failed_stage = None
        self._error_message = ""
        self.stage_messages.clear()
        self.stage_metrics.clear()

    def _validate_dependencies(self) -> None:
        """Validate that all required pipeline dependencies are initialized.

        Called at the start of ``run_pipeline()`` to catch missing
        initializations early — before they cause obscure AttributeErrors
        deep in a stage.

        Raises:
            RuntimeError: Describing which dependency is missing, with the
                attribute name so the developer can quickly locate the gap.
        """
        _required = [
            # Core LLM and tools
            "_citation_store",
            "_citation_anchor_store",
            "_citation_injector",
            "_table_generator",
            # Evidence layer
            "_evidence_store",
            "_benchmark_store",
            "_paper_knowledge_base",
            "_claim_extractor",
            "_claim_verifier",
            # Paper parsing
            "_pdf_parser",
            "_evidence_extractor",
            "_benchmark_extractor",
            "_paper_analyzer",
        ]
        missing = [attr for attr in _required if not hasattr(self, attr)]
        if missing:
            raise RuntimeError(
                f"Missing pipeline dependency: {', '.join(missing)}"
            )

    def run_pipeline(
        self,
        task: TaskInfo,
        state: StateMachine,
        feedback_queue: list,
        feedback_lock: threading.Lock,
        feedback_history: list,
        on_progress: Optional[ProgressCallback] = None,
    ) -> PipelineResult:
        """Run the full survey-generation pipeline end-to-end."""
        # Validate all dependencies are initialized before pipeline execution
        self._validate_dependencies()

        self._task = task
        self._state = state
        self._feedback_queue = feedback_queue
        self._feedback_lock = feedback_lock
        self._feedback_history = feedback_history

        # Reset pipeline state
        self.execution_log = []
        self._pipeline_retry_count = 0
        self._last_failed_stage = None
        self._error_message = ""
        self._plan = ""
        self._papers = []
        self._analysis = ""
        self._draft_sections = []
        self._validation_scores = {}
        self._retrieved_queries = []
        self._pending_expansions = []
        self._pending_revisions = []
        self.latex_repair_log = None
        self._evidence_store.clear()
        self._benchmark_store.clear()
        self._paper_knowledge_base.clear()
        self._citation_store.clear()
        self._citation_anchor_store.clear()
        self._pdf_chunks.clear()
        self._evidence_refs.clear()
        self._evidence_unavailable.clear()
        self.current_stage = ""
        self.current_message = ""
        self.stage_messages.clear()
        self.stage_metrics.clear()

        try:
            return self._pipeline(on_progress)
        except Exception as e:
            logger.exception("Pipeline failed with fatal error")
            self._safe_transition(AgentState.ERROR)
            self._log("ERROR", {"error": str(e)})
            return PipelineResult(
                status="error",
                execution_log=self.execution_log,
            )

    # ------------------------------------------------------------------
    # Pipeline stages (private)
    # ------------------------------------------------------------------
    def _pipeline(self, on_progress: Optional[ProgressCallback]) -> PipelineResult:
        """Internal pipeline orchestration."""
        if self._check_interrupted():
            return PipelineResult(status="interrupted", execution_log=self.execution_log)

        # ---- Stage 1: PLANNING ----
        self._progress(on_progress, "planning", "Generating research plan?")
        plan = self._retry_on_error(
            lambda: self._generate_plan(), AgentState.PLANNING, on_progress)
        self._log("PLANNING", {"plan": plan[:300] if plan else ""})
        self._safe_transition(AgentState.RETRIEVAL)
        if self._check_interrupted():
            return PipelineResult(status="interrupted", execution_log=self.execution_log)
        fb = self._check_human_feedback(on_progress)
        # Save any papers added via feedback BEFORE retrieval, because
        # _retrieve_papers() will overwrite self._papers with its own results.
        feedback_papers = list(self._papers) if fb.get("papers_updated") else []

        # ---- Stage 2: RETRIEVAL ----
        self._progress(on_progress, "retrieval", "Searching arXiv and Semantic Scholar?")
        papers = self._retry_on_error(
            lambda: self._retrieve_papers(), AgentState.RETRIEVAL, on_progress)
        # Apply guardrail: filter papers
        papers = self._guardrails.filter_papers(papers)
        # NOTE: self._papers is intentionally NOT updated to the guardrail-filtered
        # list here — _retrieve_papers() set it to the full unfiltered result, and
        # the original code kept it that way.  The local `papers` variable carries
        # the filtered list forward for analysis; self._papers is used for the
        # reference list and citation store.

        # Merge feedback-supplemented papers (added before retrieval) into
        # self._papers, so they survive the _retrieve_papers overwrite.
        if feedback_papers:
            seen_titles = set(p.get("title", "").strip().lower() for p in self._papers if p.get("title"))
            for p in feedback_papers:
                t = p.get("title", "").strip().lower()
                if t and t not in seen_titles:
                    self._papers.append(p)
                    seen_titles.add(t)
            self._emit_progress(
                "info",
                f"Merged {len(feedback_papers)} feedback-supplemented papers "
                f"into retrieval results ({len(self._papers)} total)",
            )

        self._log("RETRIEVAL", {"paper_count": len(papers)})
        self._safe_transition(AgentState.ANALYSIS)
        if self._check_interrupted():
            return PipelineResult(status="interrupted", execution_log=self.execution_log)
        fb = self._check_human_feedback(on_progress)
        if fb.get("papers_updated"):
            papers = list(self._papers)

        # ---- Stage 3: ANALYSIS ----
        self._progress(on_progress, "analysis", "Analyzing retrieved papers?")
        analysis = self._retry_on_error(
            lambda: self._analyze_papers(papers), AgentState.ANALYSIS, on_progress)
        self._log("ANALYSIS", {"analysis_summary": (analysis or "")[:300]})
        self._safe_transition(AgentState.WRITING)
        if self._check_interrupted():
            return PipelineResult(status="interrupted", execution_log=self.execution_log)
        fb = self._check_human_feedback(on_progress)
        if fb.get("analysis_updated"):
            analysis = self._analysis

        # ---- Stage 4-6: WRITING + VALIDATION loop ----
        rounds = 0
        final_draft = ""
        while rounds <= self.config.max_retries:
            fb = self._check_human_feedback(on_progress)
            if fb.get("papers_updated"):
                papers = list(self._papers)
            if fb.get("analysis_updated"):
                analysis = self._analysis
            if self._check_interrupted():
                return PipelineResult(status="interrupted", execution_log=self.execution_log)

            # 4. WRITING
            self._progress(
                on_progress, "writing",
                f"Writing survey draft (round {rounds + 1})?",
            )
            draft = self._retry_on_error(
                lambda: self._write_survey(analysis, rounds),
                AgentState.WRITING, on_progress)

            # Apply guardrail: check output standard and fact binding
            guardrail_results = self._guardrails.check_all({"text": draft})
            blocked = [r for r in guardrail_results if r.verdict != "pass"]
            if blocked:
                logger.warning("Guardrail blocked output: %s", blocked)

            # ---- Format Repair ----
            self._progress(
                on_progress, "format_repair",
                "Applying CVPR format repair rules?",
            )
            draft = self._format_repair(draft)
            final_draft = draft
            self._log("WRITING", {"round": rounds, "length": len(draft)})
            self._safe_transition(AgentState.VALIDATION)

            # 5. VALIDATION
            self._progress(
                on_progress, "validation",
                "Running 5-dimension quality validation on CVPR-formatted draft?",
            )
            results = self._run_validators(draft)
            report = self._aggregate_results(results)
            validators_passed = sum(1 for r in results if r.passed)
            self._emit_progress(
                "info",
                f"Validation: {validators_passed}/{len(results)} passed, "
                f"overall score {report['overall_score']:.2f}",
                {
                    "validators_passed": validators_passed,
                    "validators_total": len(results),
                    "overall_score": report["overall_score"],
                },
            )
            self._log("VALIDATION", {
                "round": rounds,
                "score": round(report["overall_score"], 3),
                "passed": report["overall_passed"],
                "failures": report["failed_validators"],
            })

            if report["overall_passed"]:
                self._safe_transition(AgentState.COMPLETE)
                self._progress(on_progress, "complete", "All quality checks passed!")
                result = self._build_result(final_draft, "complete", rounds)
                # Save validation scores
                result.validation_scores = dict(self._validation_scores)
                return result

            # 6. FEEDBACK / repair
            from agent.feedback.repair_generator import RepairGenerator
            repair_gen = RepairGenerator()
            repairs = repair_gen.generate(results)
            self._log("FEEDBACK", {"round": rounds, "repairs": repairs})

            if rounds >= self.config.max_retries:
                self._safe_transition(AgentState.COMPLETE)
                self._progress(
                    on_progress, "complete",
                    f"Max retries ({self.config.max_retries}) reached. Completing with warnings.",
                )
                result = self._build_result(final_draft, "complete_with_warnings", rounds)
                result.validation_scores = dict(self._validation_scores)
                return result

            # Prepare for next iteration
            rounds += 1
            self._safe_transition(AgentState.WRITING)

            # Regenerate analysis with repair context
            analysis = self._retry_on_error(
                lambda: self._incorporate_feedback(analysis, repairs),
                AgentState.FEEDBACK, on_progress)

        # Should not reach here
        self._safe_transition(AgentState.COMPLETE)
        return self._build_result(final_draft, "complete_with_warnings", rounds)

    # ------------------------------------------------------------------
    # LLM-powered stage helpers
    # ------------------------------------------------------------------
    def _generate_plan(self) -> str:
        """Use LLM to create a structured research plan."""
        topic = self._task.topic
        keywords = ", ".join(self._task.keywords) if self._task.keywords else "none specified"
        goal = self._task.goal or "Write a comprehensive CVPR-format survey paper"

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
            f"Focus on the years {self.config.year_start}?{self.config.year_end}."
        )

        # Guardrail: rate limit check before LLM call
        self._guardrails.check_tool_call("llm_generate", {"prompt": user_msg})
        self._emit_progress("info", "Generating research plan...")

        resp = self._safe_llm_call(sys_prompt, user_msg)
        self._plan = resp.text
        # Count sections for the metrics
        section_count = sum(1 for l in resp.text.split("\n")
                            if l.strip().startswith(("\\section", "- **", "###")))
        self._emit_progress(
            "success", f"Research plan generated with {section_count} sections",
            {"sections_count": section_count},
        )
        return resp.text

    def _retrieve_papers(self) -> list[dict]:
        """Search arXiv and Semantic Scholar, merge and dedup results.

        Two-phase retrieval:
          Phase 1 - Search for survey/review papers, then fetch their references
          Phase 2 - Search for method/benchmark/direction-specific papers
        """
        topic = self._task.topic
        keywords = self._task.keywords or [topic]
        year_start = self.config.year_start
        year_end = self.config.year_end

        # ---- Generate multi-strategy queries ----
        sys_prompt = (
            "You are a literature search strategist. "
            "Generate search queries for a survey on the given topic. "
            "Produce exactly 4 queries, one per line, no numbering, no explanation.\n"
            "Strategy 1 — Survey/review: find comprehensive survey papers.\n"
            "Strategy 2 — Method + benchmark: find papers using standard benchmarks.\n"
            "Strategy 3 — Specific technique: find papers using modern methods.\n"
            "Strategy 4 — Sub-direction: find papers in a specific sub-area.\n"
            "Example for 'edge detection':\n"
            "edge detection survey deep learning\n"
            "edge detection BSDS500 benchmark\n"
            "edge detection transformer\n"
            "edge detection self-supervised"
        )
        user_msg = (
            f"Survey topic: {topic}\n"
            f"Keywords: {', '.join(keywords)}\n"
            f"Time range: {year_start}–{year_end}\n\n"
            "Generate 4 search queries (one per strategy)."
        )

        self._guardrails.check_tool_call("llm_generate", {"prompt": user_msg})
        resp = self._safe_llm_call(sys_prompt, user_msg, use_tools=True)

        # Parse queries
        raw_lines = resp.text.strip().split("\n")
        queries = []
        for line in raw_lines:
            line = line.strip().strip('"').strip("'").strip("-").strip()
            if (line
                and len(line) < 200
                and not line.lower().startswith(("here", "sure", "ok", "i'll", "let", "the", "for", "of course"))
                and not line.startswith(("1.", "2.", "3.", "4.", "-", "*"))
            ):
                queries.append(line)

        # Fallback: ensure we have survey queries and method queries
        strategy_queries = []
        has_survey = any("survey" in q.lower() or "review" in q.lower() for q in queries)
        if has_survey:
            survey_queries = [q for q in queries if "survey" in q.lower() or "review" in q.lower()]
            method_queries = [q for q in queries if q not in survey_queries]
        else:
            survey_queries = [f"{topic} survey"]
            method_queries = queries if queries else [topic]

        if not method_queries:
            method_queries = [topic, f"{topic} {' '.join(keywords[:3])}"]

        self._emit_progress(
            "success", f"Generated {len(survey_queries)} survey + {len(method_queries)} method queries",
            {
                "queries_total": len(survey_queries) + len(method_queries),
                "survey_queries": len(survey_queries),
                "method_queries": len(method_queries),
            },
        )

        # ---- Helper: search a single query ----
        _search_lock = threading.Lock()
        all_results: list[dict] = []

        def _search_arxiv(tool, q: str) -> None:
            if not tool:
                return
            res = tool.execute({
                "query": q, "max_results": max(50, self._task.max_papers * 2),
                "year_start": year_start, "year_end": year_end,
            })
            if res.success:
                with _search_lock:
                    all_results.append(res.data)

        def _search_ss(tool, q: str) -> None:
            if not tool:
                return
            res = tool.execute({
                "query": q, "max_results": max(50, self._task.max_papers * 2),
                "year_start": year_start, "year_end": year_end,
            })
            if res.success:
                with _search_lock:
                    all_results.append(res.data)

        arxiv_tool = self.tools.get("arxiv_search")
        ss_tool = self.tools.get("semantic_scholar_search")

        # ---- Phase 1: Search for survey papers ----
        self._emit_progress("info", "Phase 1: Searching for survey/review papers...")
        for q in survey_queries:
            _search_arxiv(arxiv_tool, q)
            _search_ss(ss_tool, q)

        # Merge and dedup phase 1 results
        merge_tool = self.tools.get("merge_results")
        sort_tool = self.tools.get("sort_by_citation")
        all_papers: list[dict] = []

        if merge_tool:
            merged = merge_tool.execute({"results": list(all_results)})
            if merged.success:
                all_papers = merged.data.get("papers", [])

        # Sort by citation count
        if sort_tool and all_papers:
            sorted_res = sort_tool.execute({"papers": all_papers})
            if sorted_res.success:
                all_papers = sorted_res.data.get("papers", all_papers)

        # ---- Phase 1b: Fetch references from top survey papers ----
        survey_papers = [p for p in all_papers
                         if "survey" in p.get("title", "").lower()
                         or "review" in p.get("title", "").lower()]
        if survey_papers:
            self._emit_progress(
                "info",
                f"Phase 1b: Fetching references from top {min(3, len(survey_papers))} survey papers...",
            )
            expanded = self._fetch_references_from_surveys(survey_papers[:3])
            if expanded:
                # Dedup against existing papers
                seen_titles = set(p.get("title", "").lower().strip() for p in all_papers if p.get("title"))
                for p in expanded:
                    t = p.get("title", "").lower().strip()
                    if t and t not in seen_titles:
                        seen_titles.add(t)
                        all_papers.append(p)
                self._emit_progress(
                    "success",
                    f"Added {len(expanded)} papers from survey references",
                    {"survey_expanded": len(expanded)},
                )

        # ---- Phase 2: Search for method/benchmark papers ----
        self._emit_progress("info", "Phase 2: Searching for method and benchmark-specific papers...")
        phase2_results: list[dict] = []
        for q in method_queries:
            _search_arxiv(arxiv_tool, q)
            _search_ss(ss_tool, q)

        # Merge phase 2 results
        phase2_merged = []
        if merge_tool:
            merged2 = merge_tool.execute({"results": list(all_results)})  # includes phase 1 results too
            if merged2.success:
                phase2_merged = merged2.data.get("papers", [])

        # Merge phase 2 into all_papers (dedup)
        seen_titles = set(p.get("title", "").lower().strip() for p in all_papers if p.get("title"))
        for p in phase2_merged:
            t = p.get("title", "").lower().strip()
            if t and t not in seen_titles:
                seen_titles.add(t)
                all_papers.append(p)

        # ---- Final sort by citation count ----
        if sort_tool:
            sorted_res = sort_tool.execute({"papers": all_papers})
            if sorted_res.success:
                all_papers = sorted_res.data.get("papers", all_papers)

        self._emit_progress(
            "success", f"Total unique papers: {len(all_papers)}",
            {"papers_found": len(all_papers)},
        )

        self._papers = all_papers[:self._task.max_papers]
        self._retrieved_queries = survey_queries + method_queries

        # Register papers in CitationStore for citation resolution
        import logging
        _log = logging.getLogger(__name__)
        for paper in self._papers:
            try:
                self._citation_store.register(paper)
            except Exception as e:
                _log.debug("Skipping citation registration: %s", e)

        # ---- PDF Download & Evidence Extraction (parallel, limited scope) ----
        self._pdf_chunks.clear()
        self._evidence_refs.clear()
        self._evidence_unavailable.clear()

        import os
        os.makedirs("output/pdfs", exist_ok=True)

        # Process PDFs for all max_papers papers (by citation count)
        pdf_limit = min(self._task.max_papers, len(self._papers))
        papers_for_pdf = sorted(
            self._papers, key=lambda p: p.get("citation_count", 0), reverse=True
        )[:pdf_limit]
        papers_with_arxiv = [p for p in papers_for_pdf if p.get("arxiv_id")]
        total_pdfs = len(papers_with_arxiv)
        self._emit_progress(
            "info",
            f"Downloading and parsing PDFs for top {total_pdfs} papers "
            f"(by citation count, limit={self._task.max_papers})...",
            {"papers_downloaded": 0, "papers_total": total_pdfs},
        )

        # Parallel PDF download + parse
        _pdf_lock = threading.Lock()

        def _process_pdf(paper: dict) -> None:
            arxiv_id = paper.get("arxiv_id", "")
            paper_id = paper.get("paper_id", arxiv_id)
            if not arxiv_id:
                return

            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            save_path = f"output/pdfs/{arxiv_id}.pdf"

            try:
                pdf_tool = self.tools.get("pdf_download")
                if not pdf_tool:
                    return

                dl_res = pdf_tool.execute({"url": pdf_url, "save_path": save_path})
                if not dl_res.success:
                    with _pdf_lock:
                        self._evidence_unavailable.add(paper_id)
                    return

                chunks = self._pdf_parser.parse(paper_id, save_path)
                if not chunks:
                    with _pdf_lock:
                        self._evidence_unavailable.add(paper_id)
                    return

                with _pdf_lock:
                    self._pdf_chunks[paper_id] = chunks

            except Exception as e:
                logger.warning("PDF processing failed for %s: %s", arxiv_id, e)
                with _pdf_lock:
                    self._evidence_unavailable.add(paper_id)

        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(_process_pdf, p) for p in papers_with_arxiv]
            for f in as_completed(futures):
                f.result()  # catch exceptions

        downloaded_count = len(self._pdf_chunks)
        self._emit_progress(
            "success",
            f"PDFs: {downloaded_count} papers downloaded and parsed "
            f"({total_pdfs - downloaded_count} failed)",
            {"papers_downloaded": downloaded_count, "papers_total": total_pdfs},
        )

        # Batch evidence extraction (reduces N LLM calls to ceil(N/batch_size))
        if self._pdf_chunks:
            self._emit_progress("info", "Extracting evidence from PDFs (batch LLM)...")
            batch_refs = self._evidence_extractor.extract_batch(
                dict(self._pdf_chunks), batch_size=5,
            )
            for pid, refs in batch_refs.items():
                self._evidence_refs.extend(refs)
                if refs:
                    self._emit_progress(
                        "success", f"Evidence: {len(refs)} refs extracted from {pid}",
                    )

        # Update metrics with final PDF count
        self._emit_progress(
            "info",
            f"Evidence: {len(self._pdf_chunks)} papers with evidence, "
            f"{len(self._evidence_unavailable)} unavailable, "
            f"{len(self._evidence_refs)} total refs",
            {"papers_downloaded": len(self._pdf_chunks)},
        )
        return self._papers

    # ------------------------------------------------------------------
    # Survey reference expansion
    # ------------------------------------------------------------------
    def _fetch_references_from_surveys(self, survey_papers: list[dict]) -> list[dict]:
        """Fetch references from survey papers using Semantic Scholar API.

        For each survey paper, look up its references (papers it cites)
        and return them as a flat list of deduplicated paper dicts.
        """
        import json
        import urllib.request

        S2_PAPER_API = "https://api.semanticscholar.org/graph/v1/paper/batch"

        # Collect paper IDs from survey papers
        paper_ids = []
        for p in survey_papers:
            pid = p.get("paper_id", "") or ""
            if pid:
                paper_ids.append(pid)
            # Also try to look up via ArXiv ID
            arxiv_id = p.get("arxiv_id", "") or ""
            if arxiv_id:
                paper_ids.append(f"ArXiv:{arxiv_id}")

        if not paper_ids:
            return []

        headers = {"User-Agent": "ScholarAgent/1.0"}
        fields = "title,authors,year,citationCount,externalIds,venue,abstract,url,references"

        try:
            data = json.dumps({"ids": paper_ids})
            req = urllib.request.Request(
                S2_PAPER_API,
                data=data.encode("utf-8"),
                headers={**headers, "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                results = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning("Failed to fetch survey references: %s", e)
            return []

        # Collect referenced papers
        expanded = []
        seen_ids = set()

        for paper_data in results:
            if paper_data is None:
                continue
            refs = paper_data.get("references", []) or []
            for ref_entry in refs:
                ref = ref_entry.get("paper", {})
                if not ref:
                    continue
                ref_id = ref.get("paperId", "")
                if ref_id and ref_id in seen_ids:
                    continue
                if ref_id:
                    seen_ids.add(ref_id)

                authors = [a.get("name", "") for a in ref.get("authors", []) if a.get("name")]
                external_ids = ref.get("externalIds", {}) or {}
                expanded.append({
                    "title": ref.get("title", ""),
                    "authors": authors,
                    "abstract": ref.get("abstract", "") or "",
                    "year": ref.get("year", 0) or 0,
                    "arxiv_id": external_ids.get("ArXiv", ""),
                    "source": "semantic_scholar",
                    "url": ref.get("url", ""),
                    "venue": ref.get("venue", ""),
                    "citation_count": ref.get("citationCount", 0) or 0,
                    "doi": external_ids.get("DOI", ""),
                    "paper_id": ref.get("paperId", ""),
                    "_from_survey": True,
                })

        logger.info(
            "Fetched %d references from %d survey papers",
            len(expanded), len(paper_ids),
        )
        return expanded

    def _analyze_papers(self, papers: list[dict]) -> str:
        """Use LLM to analyze the retrieved papers."""
        topic = self._task.topic
        keywords = self._task.keywords or [topic]

        if not papers:
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
                f"Research plan:\n{self._plan[:2000]}\n\n"
                "No papers were retrieved from external sources. "
                "Please provide a comprehensive analysis based on your knowledge "
                "of the field, including specific model names, techniques, and results."
            )
            resp = self._safe_llm_call(sys_prompt, user_msg)
            self._analysis = resp.text
            self._emit_progress("info", "No papers retrieved — generating analysis from topic knowledge...")
            # Extract and verify claims from analysis
            self._extract_and_verify_claims(papers)
            # Extract benchmarks and paper knowledge from evidence references
            self._extract_benchmarks_and_knowledge()
            # Build citation anchors from verified claims
            self._build_citation_anchors()
            return resp.text

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

        self._emit_progress(
            "info", f"Analyzing {len(papers)} papers via LLM...",
            {"papers_analyzed": 0, "total_papers": len(papers)},
        )

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

        # Include PDF-extracted evidence context so the analysis is grounded
        # in actual paper content, not just abstracts.
        from agent.evidence.context_retriever import ContextRetriever, EvidenceContextBuilder
        retriever = ContextRetriever(
            evidence_store=self._evidence_store,
            benchmark_store=self._benchmark_store,
            knowledge_base=self._paper_knowledge_base,
            max_context_tokens=600,
        )
        ev_ctx = retriever.retrieve_for_section()
        evidence_context = EvidenceContextBuilder.format(ev_ctx)

        user_msg = (
            f"Survey topic: {topic}\n\n"
            f"Research plan:\n{self._plan[:2000]}\n\n"
            f"Retrieved papers ({len(papers)} total):\n{papers_text[:15000]}\n\n"
            f"{evidence_context}"
        )

        resp = self._safe_llm_call(sys_prompt, user_msg)
        self._analysis = resp.text
        self._emit_progress(
            "success", "Paper analysis completed",
            {"papers_analyzed": len(papers), "total_papers": len(papers)},
        )
        # Extract and verify claims from analysis
        self._extract_and_verify_claims(papers)
        # Extract benchmarks and paper knowledge from evidence references
        self._extract_benchmarks_and_knowledge()
        # Build citation anchors from verified claims
        self._build_citation_anchors()
        return resp.text

    def _build_citation_anchors(self) -> None:
        """Build citation anchors from verified claims.

        Populates the CitationAnchorStore so that _build_citation_context()
        can include claim-to-citation mappings in the writing prompt.
        Failures are logged but do not block the pipeline.
        """
        self._emit_progress("info", "Building citation anchors...")
        try:
            verified = self._evidence_store.get_verified_claims()
            if verified:
                self._citation_anchor_store.build(
                    claims=verified,
                    citation_store=self._citation_store,
                    paper_knowledge_base=self._paper_knowledge_base,
                )
                self._emit_progress(
                    "success",
                    f"{self._citation_anchor_store.anchor_count()} citation anchors built",
                )
                logger.info(
                    "Citation anchors: %d built from %d verified claims",
                    self._citation_anchor_store.anchor_count(),
                    len(verified),
                )
            else:
                logger.info("Citation anchors: no verified claims to build from")
        except Exception as e:
            logger.warning("Citation anchor build failed: %s", e)

    def _emit_progress(self, msg_type: str, message: str, metrics: Optional[dict] = None) -> None:
        """Record a progress message and optionally update stage metrics.

        Args:
            msg_type: One of "info", "success", "warning", "error".
            message: Human-readable description of the current sub-step.
            metrics: Optional dict of quantitative indicators to merge into
                stage_metrics (e.g. {"papers_found": 5, "queries_completed": 2}).
        """
        entry = {
            "type": msg_type,
            "message": message,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self.stage_messages.append(entry)
        if metrics:
            self.stage_metrics.update(metrics)

    def _extract_benchmarks_and_knowledge(self) -> None:
        """Extract benchmark records and paper knowledge from evidence references.

        Called after paper analysis to populate the benchmark_store and
        paper_knowledge_base. Failures are logged but do not block the pipeline.
        """
        self._emit_progress("info", "Extracting benchmark data and paper knowledge...")
        try:
            if self._evidence_refs:
                # Extract benchmark records
                benchmark_records = self._benchmark_extractor.extract(self._evidence_refs)
                if benchmark_records:
                    self._benchmark_store.add_records(benchmark_records)
                    self._emit_progress(
                        "success", f"{len(benchmark_records)} benchmark records extracted",
                        {"benchmark_records": len(benchmark_records)},
                    )
                    logger.info("Evidence: %d benchmark records extracted", len(benchmark_records))
                else:
                    logger.info("Evidence: no benchmark records extracted")

                # Extract paper knowledge
                knowledge_list = self._paper_analyzer.analyze(self._evidence_refs)
                if knowledge_list:
                    for pk in knowledge_list:
                        self._paper_knowledge_base.add(pk)
                    self._emit_progress(
                        "success", f"Knowledge extracted for {len(knowledge_list)} papers",
                    )
                    logger.info("Evidence: knowledge extracted for %d papers", len(knowledge_list))
                else:
                    logger.info("Evidence: no paper knowledge extracted")
            else:
                logger.info("Evidence: no evidence refs available for benchmark/knowledge extraction")
        except Exception as e:
            logger.warning("Evidence benchmark/knowledge extraction failed: %s", e)

    def _write_survey(self, analysis: str, round_num: int) -> str:
        """Use LLM to write the survey paper in CVPR format."""
        topic = self._task.topic
        keywords = ", ".join(self._task.keywords) if self._task.keywords else topic

        refs = []
        for i, p in enumerate(self._papers, 1):
            authors = p.get("authors", [])[:3]
            author_str = ", ".join(authors) if authors else "Unknown"
            if len(p.get("authors", [])) > 3:
                author_str += " et al."
            year = p.get("year", 2024)
            title = p.get("title", "Untitled")
            refs.append(f"[{i}] {author_str}. \"{title}.\" {year}.")

        ref_text = "\n".join(refs)

        self._emit_progress(
            "success", f"Built reference list ({len(self._papers)} papers)",
        )

        if not analysis or len(analysis) < 200:
            analysis = (
                f"The survey covers the topic of {topic}. "
                f"Key areas include: efficient transformer architectures, "
                f"model compression, quantization, pruning, knowledge distillation, "
                f"hardware-aware design, and edge deployment. "
                f"Discuss recent advances and open challenges."
            )

        writing_instruction = (
            "Write a comprehensive CVPR-format survey paper on the given topic. "
            "The paper MUST be substantive: each section should have 3-5 detailed paragraphs. "
            "Use [CITE:key] markers for citations (e.g., [CITE:qwen2024]). "
            "NEVER write \\cite{} directly — the system will convert markers automatically. "
            "Use [TABLE:benchmark_MMLU] for benchmark results (the system will insert the table). "
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
            "13. Use [CITE:key] markers for citations. NEVER write \\cite{} directly.\n"
            "### END CVPR FORMAT REQUIREMENTS ###\n"
        )

        sys_prompt = (
            "You are an academic writing assistant specializing in computer vision surveys. "
            f"{writing_instruction}\n\n{cvpr_format_instructions}"
        )
        # Evidence context for factual grounding (from all three stores)
        retriever = ContextRetriever(
            evidence_store=self._evidence_store,
            benchmark_store=self._benchmark_store,
            knowledge_base=self._paper_knowledge_base,
        )
        context = retriever.retrieve_for_section()
        evidence_context = EvidenceContextBuilder.format(context)

        self._emit_progress("info", "Retrieving evidence context for factual grounding...")

        # Phase 2: Citation anchor context
        citation_context = self._build_citation_context()

        self._emit_progress(
            "info",
            f"Writing survey draft (round {round_num + 1}/{self.config.max_retries + 1})...",
            {"round": round_num + 1, "total_rounds": self.config.max_retries + 1},
        )

        # Include pending human feedback (expand_section / general) in the prompt
        human_feedback_instructions = ""
        if self._pending_expansions:
            expansions = "\n".join(f"- {e}" for e in self._pending_expansions)
            human_feedback_instructions += (
                "\n\n### HUMAN REQUEST: Expand these sections ###\n"
                f"{expansions}\n"
                "Please add substantial new content addressing these topics. "
                "Add new subsections if needed.\n"
            )
            self._pending_expansions.clear()
        if self._pending_revisions:
            revisions = "\n".join(f"- {r}" for r in self._pending_revisions)
            human_feedback_instructions += (
                "\n\n### HUMAN REQUEST: Apply these revisions ###\n"
                f"{revisions}\n"
                "Please incorporate these changes into the appropriate sections.\n"
            )
            self._pending_revisions.clear()

        user_msg = (
            f"Title: A Comprehensive Survey on {topic}\n"
            f"Keywords: {keywords}\n\n"
            f"Research Plan:\n{self._plan[:3000]}\n\n"
            f"Paper Analysis:\n{analysis[:15000]}\n\n"
            f"References:\n{ref_text}\n\n"
            f"{evidence_context}\n\n"
            f"{citation_context}\n\n"
            f"{human_feedback_instructions}\n\n"
            f"Round {round_num + 1} of up to {self.config.max_retries + 1}.\n\n"
            "IMPORTANT: Write the COMPLETE survey paper with all sections. "
            "Each section must have substantive technical content. "
            "Do not leave any section empty or as a placeholder."
        )

        resp = self._safe_llm_call(sys_prompt, user_msg)
        self._draft_sections = self._extract_sections(resp.text)
        word_count = len(resp.text.split())
        self._emit_progress(
            "success",
            f"Draft written ({word_count} words, {len(self._draft_sections)} sections)",
            {"sections_count": len(self._draft_sections), "word_count": word_count},
        )

        self._emit_progress("info", "Post-processing: injecting citations and generating tables...")
        # Phase 2: Post-process — inject citations and generate tables
        draft = self._post_process(resp.text)

        return draft

    def _build_citation_context(self) -> str:
        """Build a citation key context for the writing prompt.

        Lists available citation keys from the CitationStore so the LLM
        can use them in [CITE:key] markers.
        """
        if self._citation_store.entry_count() == 0:
            return ""

        lines: list[str] = []
        lines.append("=== Citation Context ===")
        lines.append("Available citation keys (use [CITE:key] to reference):")

        for entry in self._citation_store.get_all_entries():
            model_info = ""
            if entry.model_names:
                model_info = f"  [models: {', '.join(entry.model_names[:3])}]"
            lines.append(
                f"  [CITE:{entry.citation_key}] — {entry.title[:80]}{model_info}"
            )

        # Add anchor info if available
        anchors = self._citation_anchor_store.get_anchors()
        if anchors:
            lines.append("")
            lines.append("Claim-to-citation mappings:")
            for anchor in anchors[:10]:  # Limit to top 10
                lines.append(
                    f"  \"{anchor.claim_text[:60]}\" → [CITE:{anchor.citation_key}]"
                )

        lines.append("=== End Citation Context ===")
        return "\n".join(lines)

    def _post_process(self, draft: str) -> str:
        """Run deterministic post-processing on the draft.

        Steps:
          1. Replace [CITE:key] markers with \\cite{key} (CitationInjector).
          2. Replace [TABLE:...] markers with generated LaTeX tables.
        """
        if not draft:
            return draft

        # Step 1: Inject citations
        draft = self._citation_injector.inject(draft)

        # Step 2: Generate tables (requires benchmark_store from pipeline context)
        if self._benchmark_store:
            draft = self._table_generator.replace_tables(draft)

        return draft

    def _extract_and_verify_claims(self, papers: list[dict]) -> None:
        """Extract claims from analysis and verify them against paper sources.

        Called at the end of _analyze_papers() for each code path.
        Failures are logged but do not block the pipeline.
        """
        self._emit_progress("info", "Extracting claims from analysis...")
        try:
            claims = self._claim_extractor.extract(self._analysis, papers)
            if claims:
                self._evidence_store.add_claims(claims)
                self._emit_progress("success", f"Extracted {len(claims)} claims", {"claims_extracted": len(claims)})
                self._claim_verifier.verify_all(self._evidence_store, papers)
                verified_count = self._evidence_store.verified_count()
                self._emit_progress(
                    "success", f"{verified_count}/{len(claims)} claims verified",
                    {"claims_verified": verified_count},
                )
                logger.info(
                    "Evidence: %d claims extracted, %d verified",
                    len(claims),
                    verified_count,
                )
            else:
                logger.info("Evidence: no claims extracted from analysis")
        except Exception as e:
            logger.warning("Evidence extraction/verification failed: %s", e)

    def _incorporate_feedback(self, analysis: str, repairs: str) -> str:
        """Use LLM to revise the analysis based on validation feedback."""
        if not repairs:
            return analysis

        sys_prompt = (
            "You are a research revision assistant. "
            "Revise the paper analysis to address the following quality issues. "
            "Keep the original structure but improve the flagged aspects."
        )
        user_msg = (
            f"Original plan:\n{self._plan[:1000]}\n\n"
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
        paper_ids = []
        for match in re.finditer(r'\\cite\{([^}]+)\}', draft):
            for ref in match.group(1).split(","):
                paper_ids.append(ref.strip())
        for match in re.finditer(r'\[@(\w+)\]', draft):
            paper_ids.append(match.group(1))

        context = {
            "content": draft or " ",
            "paper_ids": list(set(paper_ids)) if paper_ids else ["ref"],
        }
        results = []
        for v in self._validators:
            vname = v.__class__.__name__
            self._emit_progress("info", f"Running validator: {vname}...")
            try:
                result = v.validate(context)
                results.append(result)
                if result.passed:
                    self._emit_progress(
                        "success", f"{vname}: passed (score {result.score:.2f})",
                    )
                else:
                    self._emit_progress(
                        "warning", f"{vname}: needs improvement (score {result.score:.2f})",
                    )
            except Exception as e:
                self._emit_progress("error", f"{vname}: failed with error: {e}")
                from agent.feedback.base import ValidationResult
                results.append(ValidationResult(
                    validator_name=vname,
                    score=0.0, passed=False,
                    repair_instructions=f"Validator crashed: {e}",
                ))

        self._validation_scores = {
            r.validator_name: {
                "score": r.score,
                "passed": r.passed,
                "message": (r.repair_instructions or "")[:200],
            }
            for r in results
        }
        return results

    def _aggregate_results(self, results: list[ValidationResult]) -> dict:
        """Aggregate validation results into a summary dict."""
        from agent.feedback.aggregator import FeedbackAggregator
        aggregator = FeedbackAggregator(pass_threshold=self.config.quality_threshold)
        report = aggregator.aggregate(results)
        return {
            "overall_score": report.overall_score,
            "overall_passed": report.overall_passed,
            "failed_validators": report.failed_validators,
        }

    # ------------------------------------------------------------------
    # Human feedback handling
    # ------------------------------------------------------------------
    def _check_human_feedback(self, on_progress: Optional[ProgressCallback]) -> dict:
        """Check and process pending feedback at stage boundaries.

        Returns a dict with flags indicating what changed:
          - papers_updated: True if papers were supplemented
          - analysis_updated: True if analysis was re-generated
        """
        result: dict = {"papers_updated": False, "analysis_updated": False}
        with self._feedback_lock:
            if not self._feedback_queue:
                return result
            feedback = self._feedback_queue.pop(0)
            feedback["status"] = "processing"
            # Append to feedback_history (owned by Harness, referenced via self._feedback_history)
            self._feedback_history.append(feedback)

        short = feedback["content"][:60]
        self._progress(on_progress, "feedback", f"Processing feedback ({feedback['category']}): {short}?")

        if feedback["category"] == "supplement_papers":
            self._progress(on_progress, "retrieval", f"Supplementing papers: {short}?")
            new_papers = self._supplement_retrieval(feedback["content"])
            self._papers.extend(new_papers)
            seen_titles = set()
            deduped = []
            for p in self._papers:
                t = (p.get("title") or "").strip().lower()
                if t and t not in seen_titles:
                    seen_titles.add(t)
                    deduped.append(p)
            self._papers = deduped
            self._progress(on_progress, "analysis", "Re-analyzing with supplemented papers?")
            self._analysis = self._analyze_papers(self._papers)
            result["papers_updated"] = True
            result["analysis_updated"] = True

        elif feedback["category"] == "expand_section":
            self._pending_expansions.append(feedback["content"])

        elif feedback["category"] == "general":
            self._pending_revisions.append(feedback["content"])

        feedback["status"] = "applied"
        self._progress(on_progress, "feedback", f"Feedback applied: {short}?")
        return result

    def _supplement_retrieval(self, feedback_content: str) -> list[dict]:
        """Perform additional paper retrieval based on feedback content."""
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
        arxiv_tool = self.tools.get("arxiv_search")
        if arxiv_tool:
            arxiv_res = arxiv_tool.execute({"query": query, "max_results": 10})
            if arxiv_res.success:
                all_results.append(arxiv_res.data)

        ss_tool = self.tools.get("semantic_scholar_search")
        if ss_tool:
            ss_res = ss_tool.execute({"query": query, "max_results": 10})
            if ss_res.success:
                all_results.append(ss_res.data)

        time.sleep(0.3)
        merge_tool = self.tools.get("merge_results")
        if merge_tool:
            merged = merge_tool.execute({"results": all_results})
            return merged.data.get("papers", []) if merged.success else []
        return []

    # ------------------------------------------------------------------
    # Error recovery helpers
    # ------------------------------------------------------------------
    def _ensure_state(self, target: AgentState) -> None:
        """Transition to target state if not already there."""
        if self._state.current_state != target:
            self._safe_transition(target)

    def _retry_on_error(
        self,
        fn: Callable[[], Any],
        stage: AgentState,
        on_progress: Optional[ProgressCallback],
    ) -> Any:
        """Execute a stage function with phase-level retry."""
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
                    wait = 2 ** attempt
                    logger.warning(
                        "Stage %s failed (attempt %d/%d): %s. Retrying in %ds ?",
                        stage.name, attempt, self.config.max_pipeline_retries + 1, e, wait,
                    )
                    self._progress(
                        on_progress, "retrying",
                        f"? {stage.name} failed (attempt {attempt}/"
                        f"{self.config.max_pipeline_retries + 1}): "
                        f"{e!s:.80}. Retrying in {wait}s ?",
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "Stage %s failed after %d attempts. Giving up.",
                        stage.name, self.config.max_pipeline_retries + 1,
                    )
                    raise

    # ------------------------------------------------------------------
    # Format repair
    # ------------------------------------------------------------------
    def _format_repair(self, draft: str) -> str:
        """Run CVPR format repair on the LaTeX draft."""
        self._emit_progress("info", "Running CVPR format repair...")
        repair_log = self._latex_repair.repair(draft)
        self.latex_repair_log = repair_log

        if repair_log.has_changes:
            self._emit_progress(
                "success",
                f"Format repair: {repair_log.change_count} issue(s) fixed",
                {"changes_count": repair_log.change_count},
            )
            logger.info(
                "CVPR format repair: %d change(s) applied",
                repair_log.change_count,
            )
            for entry in repair_log.entries:
                logger.debug("  %s", entry.short())
        else:
            self._emit_progress("success", "Format repair: no changes needed")
            logger.info("CVPR format repair: no changes needed")

        return repair_log.fixed_text

    # ------------------------------------------------------------------
    # Interrupt support
    # ------------------------------------------------------------------
    def _check_interrupted(self) -> bool:
        """Check if the pipeline has been interrupted.

        Returns True if interrupted, in which case the caller should
        return early.
        """
        if self._interrupt_event and self._interrupt_event.is_set():
            logger.info("Pipeline interrupted -- exiting stage loop")
            return True
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _safe_llm_call(self, system_prompt: str, user_message: str, use_tools: bool = False) -> LLMResponse:
        """Call LLM with optional tool definitions."""
        try:
            tools = None
            if use_tools:
                # Build tool definitions from the ToolRegistry
                tools = []
                for name in self.tools.list_tools():
                    tool = self.tools.get(name)
                    if tool:
                        tools.append({
                            "type": "function",
                            "function": {
                                "name": name,
                                "description": getattr(tool, "description", ""),
                                "parameters": {"type": "object", "properties": {}},
                            },
                        })
            return self.llm.generate(system_prompt, user_message, tools=tools)
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            raise RuntimeError(f"LLM call failed: {e}") from e

    def _safe_transition(self, target: AgentState) -> None:
        """Attempt a state transition; log and swallow if invalid."""
        try:
            self._state.transition_to(target)
        except ValueError as e:
            logger.warning("State transition skipped: %s", e)

    def _progress(self, cb: Optional[ProgressCallback], stage: str, msg: str) -> None:
        """Dispatch progress callback if set."""
        self.current_stage = stage
        self.current_message = msg
        detail = self._build_task_info()
        # Include last 20 messages to keep WebSocket payload bounded
        detail["stage_messages"] = self.stage_messages[-20:]
        detail["stage_metrics"] = dict(self.stage_metrics)
        if cb:
            cb(stage, msg, detail)

    def _log(self, stage: str, data: dict) -> None:
        """Append to execution log with timestamp."""
        self.execution_log.append({
            "stage": stage,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **data,
        })

    def _build_result(self, paper: str, status: str, rounds: int) -> PipelineResult:
        """Build the final PipelineResult."""
        result = PipelineResult(
            paper=paper,
            status=status,
            rounds=rounds,
            execution_log=list(self.execution_log),
            validation_scores=dict(self._validation_scores),
        )
        if self.latex_repair_log is not None:
            result.latex_repair_log = {
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

    def _build_task_info(self) -> dict:
        """Build a task info dict for progress callbacks."""
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
            for p in self._papers[:10]:
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
                "preview": self._analysis[:300],
            }
        if self._draft_sections:
            details["sections"] = self._draft_sections
        if self._validation_scores:
            details["validation"] = self._validation_scores
        return details

    @staticmethod
    def _extract_sections(draft: str) -> list[dict]:
        """Extract section structure from a LaTeX draft."""
        sections = []
        for match in re.finditer(r'\\(?:sub)*section\{([^}]+)\}', draft):
            sections.append({
                "level": match.group(0).count("sub"),
                "title": match.group(1),
            })
        return sections