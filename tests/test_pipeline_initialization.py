"""Integration tests for PipelineOrchestrator initialization.

Verifies that all pipeline dependencies are properly initialized
before pipeline execution, preventing AttributeErrors during stages.
"""
import threading
import pytest

from agent.core.state import AgentState, StateMachine
from agent.core.pipeline import (
    HarnessConfig,
    PipelineOrchestrator,
    PipelineResult,
    TaskInfo,
)
from agent.core.llm import MockLLM
from agent.guardrails.manager import GuardrailManager
from agent.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_orchestrator():
    """Create a minimal PipelineOrchestrator for testing."""
    llm = MockLLM(fixed_response="Test response")
    tools = ToolRegistry()
    guardrails = GuardrailManager(guardrails=[])
    config = HarnessConfig()
    return PipelineOrchestrator(
        llm=llm,
        tools=tools,
        validators=[],
        guardrails=guardrails,
        config=config,
        latex_repair=None,
    )


# ---------------------------------------------------------------------------
# Tests: Initialization completeness
# ---------------------------------------------------------------------------

class TestPipelineInitialization:
    """Verify all pipeline dependencies are initialized."""

    def test_evidence_store_initialized(self):
        """_evidence_store must be initialized."""
        orch = _make_orchestrator()
        assert orch._evidence_store is not None

    def test_benchmark_store_initialized(self):
        """_benchmark_store must be initialized."""
        orch = _make_orchestrator()
        assert orch._benchmark_store is not None

    def test_paper_knowledge_base_initialized(self):
        """_paper_knowledge_base must be initialized."""
        orch = _make_orchestrator()
        assert orch._paper_knowledge_base is not None

    def test_citation_anchor_store_initialized(self):
        """_citation_anchor_store must be initialized (the reported bug)."""
        orch = _make_orchestrator()
        assert orch._citation_anchor_store is not None

    def test_citation_injector_initialized(self):
        """_citation_injector must be initialized."""
        orch = _make_orchestrator()
        assert orch._citation_injector is not None

    def test_table_generator_initialized(self):
        """_table_generator must be initialized."""
        orch = _make_orchestrator()
        assert orch._table_generator is not None

    def test_claim_extractor_initialized(self):
        """_claim_extractor must be initialized."""
        orch = _make_orchestrator()
        assert orch._claim_extractor is not None

    def test_claim_verifier_initialized(self):
        """_claim_verifier must be initialized."""
        orch = _make_orchestrator()
        assert orch._claim_verifier is not None

    def test_evidence_extractor_initialized(self):
        """_evidence_extractor must be initialized."""
        orch = _make_orchestrator()
        assert orch._evidence_extractor is not None

    def test_benchmark_extractor_initialized(self):
        """_benchmark_extractor must be initialized."""
        orch = _make_orchestrator()
        assert orch._benchmark_extractor is not None

    def test_paper_analyzer_initialized(self):
        """_paper_analyzer must be initialized."""
        orch = _make_orchestrator()
        assert orch._paper_analyzer is not None

    def test_citation_store_initialized(self):
        """_citation_store must be initialized."""
        orch = _make_orchestrator()
        assert orch._citation_store is not None

    def test_pdf_parser_initialized(self):
        """_pdf_parser must be initialized."""
        orch = _make_orchestrator()
        assert orch._pdf_parser is not None

    def test_all_evidence_layer_components_distinct(self):
        """All evidence layer components should be distinct instances."""
        orch = _make_orchestrator()
        assert orch._evidence_store is not orch._benchmark_store
        assert orch._citation_store is not orch._citation_anchor_store
        assert orch._citation_injector is not orch._table_generator
        assert orch._claim_extractor is not orch._claim_verifier

    def test_citation_injector_has_store(self):
        """CitationInjector should hold a reference to the CitationStore."""
        orch = _make_orchestrator()
        assert orch._citation_injector._store is orch._citation_store

    def test_table_generator_has_stores(self):
        """BenchmarkTableGenerator should hold references to BenchmarkStore and CitationStore."""
        orch = _make_orchestrator()
        assert orch._table_generator._benchmark_store is orch._benchmark_store
        assert orch._table_generator._citation_store is orch._citation_store


# ---------------------------------------------------------------------------
# Tests: _validate_dependencies
# ---------------------------------------------------------------------------

class TestValidateDependencies:
    """Verify the startup validation catches missing dependencies."""

    def test_validate_passes_with_full_init(self):
        """_validate_dependencies should pass when all deps are present."""
        orch = _make_orchestrator()
        # Should not raise
        orch._validate_dependencies()

    def test_validate_raises_on_missing_attr(self):
        """_validate_dependencies should raise RuntimeError for missing attr."""
        orch = _make_orchestrator()
        # Simulate a missing dependency
        saved = getattr(orch, "_citation_anchor_store", None)
        try:
            del orch._citation_anchor_store
            with pytest.raises(RuntimeError) as exc:
                orch._validate_dependencies()
            assert "_citation_anchor_store" in str(exc.value)
        finally:
            if saved is not None:
                orch._citation_anchor_store = saved

    def test_validate_raises_on_multiple_missing(self):
        """_validate_dependencies should list all missing deps."""
        orch = _make_orchestrator()
        saved = []
        for attr in ("_citation_anchor_store", "_citation_injector", "_table_generator"):
            saved.append((attr, getattr(orch, attr, None)))
            try:
                delattr(orch, attr)
            except AttributeError:
                pass
        try:
            with pytest.raises(RuntimeError) as exc:
                orch._validate_dependencies()
            msg = str(exc.value)
            assert "_citation_anchor_store" in msg
            assert "_citation_injector" in msg
            assert "_table_generator" in msg
        finally:
            for attr, val in saved:
                if val is not None:
                    setattr(orch, attr, val)

    def test_validate_error_message_format(self, capsys):
        """Error message should follow the format: 'Missing pipeline dependency: ...'."""
        orch = _make_orchestrator()
        try:
            old = orch._evidence_store
            del orch._evidence_store
            with pytest.raises(RuntimeError) as exc:
                orch._validate_dependencies()
            assert "Missing pipeline dependency:" in str(exc.value)
            assert "_evidence_store" in str(exc.value)
        finally:
            orch._evidence_store = old


# ---------------------------------------------------------------------------
# Tests: Run pipeline (end-to-end smoke test)
# ---------------------------------------------------------------------------

class TestPipelineRuns:
    """Verify the pipeline runs without AttributeErrors from missing deps."""

    def test_run_pipeline_basic(self):
        """run_pipeline should complete without AttributeError for missing deps."""
        orch = _make_orchestrator()
        task = TaskInfo(topic="Test Topic", keywords=["test"], goal="Test goal")
        state = StateMachine()
        state.transition_to(AgentState.PLANNING)

        result = orch.run_pipeline(
            task=task,
            state=state,
            feedback_queue=[],
            feedback_lock=threading.Lock(),
            feedback_history=[],
        )

        assert isinstance(result, PipelineResult)
        # The pipeline may fail due to missing tools, but should NOT
        # fail with AttributeError for missing _citation_anchor_store
        assert result.status in ("error", "interrupted", "complete_with_warnings")
        # Check no AttributeError in the execution log
        for entry in result.execution_log:
            err = entry.get("error", "")
            assert "AttributeError" not in err, (
                f"Pipeline raised AttributeError: {err}"
            )
            assert "_citation_anchor_store" not in err
            assert "_citation_injector" not in err
            assert "_table_generator" not in err

    def test_validate_dependencies_called_at_start(self, monkeypatch):
        """_validate_dependencies should be called at the beginning of run_pipeline."""
        import agent.core.pipeline as pipeline_mod
        original = pipeline_mod.PipelineOrchestrator._validate_dependencies
        called = []

        def tracking_validate(self):
            called.append(True)
            return original(self)

        monkeypatch.setattr(
            pipeline_mod.PipelineOrchestrator,
            "_validate_dependencies",
            tracking_validate,
        )

        orch = _make_orchestrator()
        task = TaskInfo(topic="Test Topic", keywords=["test"], goal="Test goal")
        state = StateMachine()
        state.transition_to(AgentState.PLANNING)

        orch.run_pipeline(
            task=task,
            state=state,
            feedback_queue=[],
            feedback_lock=threading.Lock(),
            feedback_history=[],
        )

        assert len(called) == 1, "_validate_dependencies was not called by run_pipeline"
