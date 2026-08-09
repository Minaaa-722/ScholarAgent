import json
import logging
import re
import threading
import time
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
    max_papers: int = 20


@dataclass
class HarnessConfig:
    max_papers: int = 20
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
        self._check_human_feedback(on_progress)

        # ---- Stage 2: RETRIEVAL ----
        self._progress(on_progress, "retrieval", "Searching arXiv and Semantic Scholar?")
        papers = self._retry_on_error(
            lambda: self._retrieve_papers(), AgentState.RETRIEVAL, on_progress)
        # Apply guardrail: filter papers
        papers = self._guardrails.filter_papers(papers)
        self._log("RETRIEVAL", {"paper_count": len(papers)})
        self._safe_transition(AgentState.ANALYSIS)
        if self._check_interrupted():
            return PipelineResult(status="interrupted", execution_log=self.execution_log)
        self._check_human_feedback(on_progress)

        # ---- Stage 3: ANALYSIS ----
        self._progress(on_progress, "analysis", "Analyzing retrieved papers?")
        analysis = self._retry_on_error(
            lambda: self._analyze_papers(papers), AgentState.ANALYSIS, on_progress)
        self._log("ANALYSIS", {"analysis_summary": (analysis or "")[:300]})
        self._safe_transition(AgentState.WRITING)
        if self._check_interrupted():
            return PipelineResult(status="interrupted", execution_log=self.execution_log)
        self._check_human_feedback(on_progress)

        # ---- Stage 4-6: WRITING + VALIDATION loop ----
        rounds = 0
        final_draft = ""
        while rounds <= self.config.max_retries:
            self._check_human_feedback(on_progress)
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
        """Search arXiv and Semantic Scholar, merge and dedup results."""
        topic = self._task.topic
        keywords = self._task.keywords or [topic]

        # Generate search queries via LLM, with robust parsing
        sys_prompt = (
            "You are a literature search assistant. "
            "Generate exactly 3 concise search queries to find papers for a survey. "
            "Return ONLY the 3 queries, one per line, no numbering, no explanation."
        )
        user_msg = f"Survey topic: {topic}\nKeywords: {', '.join(keywords)}\n\nGenerate 3 search queries."

        # Guardrail: rate limit check
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
                and not line.startswith(("1.", "2.", "3.", "-", "*"))
            ):
                queries.append(line)

        if len(queries) < 1:
            queries = [topic]
        if len(queries) < 2:
            queries.append(f"{topic} survey")
        if len(queries) < 3:
            queries.append(f"{' '.join(keywords[:3])}")

        self._emit_progress(
            "success", f"Generated {len(queries)} search queries",
            {"queries_total": len(queries), "queries_completed": 0},
        )

        # Search both sources
        all_results = []
        for i, q in enumerate(queries):
            self._emit_progress(
                "info",
                f"Searching arXiv with query {i+1}/{len(queries)}: \"{q[:60]}\"",
            )
            arxiv_tool = self.tools.get("arxiv_search")
            if arxiv_tool:
                arxiv_res = arxiv_tool.execute({
                    "query": q, "max_results": self.config.max_papers,
                })
                if arxiv_res.success:
                    papers_count = len(arxiv_res.data.get("papers", []))
                    self._emit_progress(
                        "success", f"arXiv: found {papers_count} papers",
                    )
                    all_results.append(arxiv_res.data)
                else:
                    self._emit_progress("warning", f"arXiv search failed for query: {q[:60]}")

            self._emit_progress(
                "info",
                f"Searching Semantic Scholar with query {i+1}/{len(queries)}: \"{q[:60]}\"",
            )
            ss_tool = self.tools.get("semantic_scholar_search")
            if ss_tool:
                ss_res = ss_tool.execute({
                    "query": q, "max_results": self.config.max_papers,
                })
                if ss_res.success:
                    papers_count = len(ss_res.data.get("papers", []))
                    self._emit_progress(
                        "success", f"Semantic Scholar: found {papers_count} papers",
                    )
                    all_results.append(ss_res.data)
                else:
                    self._emit_progress("warning", f"Semantic Scholar search failed for query: {q[:60]}")

            time.sleep(0.3)

        # Merge and dedup
        merge_tool = self.tools.get("merge_results")
        merged = merge_tool.execute({"results": all_results}) if merge_tool else type('', (), {})()
        papers = merged.data.get("papers", []) if hasattr(merged, 'success') and merged.success else []
        self._emit_progress(
            "success", f"Merged and deduplicated: {len(papers)} unique papers",
            {"papers_found": len(papers)},
        )

        # Sort by citation count
        sort_tool = self.tools.get("sort_by_citation")
        if sort_tool:
            sorted_res = sort_tool.execute({"papers": papers})
            papers = sorted_res.data.get("papers", papers) if sorted_res.success else papers
        self._emit_progress("success", f"Sorted {len(papers)} papers by citation count")

        self._papers = papers[:self.config.max_papers]
        self._retrieved_queries = queries

        # Register papers in CitationStore for citation resolution
        import logging
        _log = logging.getLogger(__name__)
        for paper in self._papers:
            try:
                self._citation_store.register(paper)
            except Exception as e:
                _log.debug("Skipping citation registration: %s", e)

        # ---- PDF Download & Evidence Extraction ----
        self._pdf_chunks.clear()
        self._evidence_refs.clear()
        self._evidence_unavailable.clear()

        import os
        os.makedirs("output/pdfs", exist_ok=True)

        papers_with_arxiv = [p for p in self._papers if p.get("arxiv_id")]
        total_pdfs = len(papers_with_arxiv)
        self._emit_progress(
            "info", f"Downloading and parsing PDFs ({total_pdfs} papers with arXiv IDs)...",
        )

        for idx, paper in enumerate(papers_with_arxiv, 1):
            arxiv_id = paper.get("arxiv_id", "")
            paper_id = paper.get("paper_id", arxiv_id)
            if not arxiv_id:
                continue

            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            save_path = f"output/pdfs/{arxiv_id}.pdf"

            self._emit_progress(
                "info",
                f"Downloading PDF ({idx}/{total_pdfs}): {arxiv_id}",
                {"papers_downloaded": idx - 1, "papers_total": total_pdfs},
            )

            try:
                # Download PDF
                pdf_tool = self.tools.get("pdf_download")
                if pdf_tool:
                    dl_res = pdf_tool.execute({"url": pdf_url, "save_path": save_path})
                    if not dl_res.success:
                        self._emit_progress(
                            "warning",
                            f"PDF download failed for {arxiv_id}: {dl_res.error}",
                        )
                        self._evidence_unavailable.add(paper_id)
                        continue
                else:
                    # No PDF download tool available -- skip
                    continue

                # Parse into chunks
                chunks = self._pdf_parser.parse(paper_id, save_path)
                if not chunks:
                    self._emit_progress("warning", f"PDF parsing returned no chunks for {arxiv_id}")
                    self._evidence_unavailable.add(paper_id)
                    continue

                self._pdf_chunks[paper_id] = chunks

                # Extract evidence references
                refs = self._evidence_extractor.extract(chunks)
                if refs:
                    self._evidence_refs.extend(refs)
                    self._emit_progress(
                        "success", f"Evidence: {len(refs)} refs extracted from {arxiv_id}",
                    )
                else:
                    self._emit_progress("info", f"Evidence: no refs extracted from {arxiv_id}")

            except Exception as e:
                self._emit_progress("warning", f"Evidence extraction failed for {arxiv_id}: {e}")
                self._evidence_unavailable.add(paper_id)

        # Update metrics with final PDF count
        self._emit_progress(
            "info",
            f"Evidence: {len(self._pdf_chunks)} papers with evidence, "
            f"{len(self._evidence_unavailable)} unavailable, "
            f"{len(self._evidence_refs)} total refs",
            {"papers_downloaded": len(self._pdf_chunks)},
        )
        return self._papers

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
        user_msg = (
            f"Survey topic: {topic}\n\n"
            f"Research plan:\n{self._plan[:2000]}\n\n"
            f"Retrieved papers ({len(papers)} total):\n{papers_text[:15000]}"
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

        # Phase 2: Citation anchor context
        citation_context = self._build_citation_context()

        user_msg = (
            f"Title: A Comprehensive Survey on {topic}\n"
            f"Keywords: {keywords}\n\n"
            f"Research Plan:\n{self._plan[:3000]}\n\n"
            f"Paper Analysis:\n{analysis[:6000]}\n\n"
            f"References:\n{ref_text}\n\n"
            f"{evidence_context}\n\n"
            f"{citation_context}\n\n"
            f"Round {round_num + 1} of up to {self.config.max_retries + 1}.\n\n"
            "IMPORTANT: Write the COMPLETE survey paper with all sections. "
            "Each section must have substantive technical content. "
            "Do not leave any section empty or as a placeholder."
        )

        resp = self._safe_llm_call(sys_prompt, user_msg)
        self._draft_sections = self._extract_sections(resp.text)

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
    def _check_human_feedback(self, on_progress: Optional[ProgressCallback]) -> None:
        """Check and process pending feedback at stage boundaries."""
        with self._feedback_lock:
            if not self._feedback_queue:
                return
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

        elif feedback["category"] == "expand_section":
            self._pending_expansions.append(feedback["content"])

        elif feedback["category"] == "general":
            self._pending_revisions.append(feedback["content"])

        feedback["status"] = "applied"
        self._progress(on_progress, "feedback", f"Feedback applied: {short}?")

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
        repair_log = self._latex_repair.repair(draft)
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