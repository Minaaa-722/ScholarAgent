"""Paper analyzer for the evidence grounding layer.

Extracts structured PaperKnowledge from EvidenceReference objects using
LLM prompts. Organizes evidence into per-paper knowledge with per-field
evidence_refs for traceability.
"""

import json
import logging
from typing import Optional

from agent.core.llm import LLMBase
from agent.evidence.evidence_reference import (
    EvidenceReference,
    KnowledgeField,
    DatasetReference,
)
from agent.evidence.paper_knowledge import (
    ArchitectureKnowledge,
    TrainingKnowledge,
    PaperKnowledge,
)

logger = logging.getLogger(__name__)


class PaperAnalyzer:
    """Extracts structured PaperKnowledge from EvidenceReference objects.

    Takes already-extracted evidence references and organizes them into
    structured per-paper knowledge. Each KnowledgeField gets its own
    evidence_refs for traceability.
    """

    def __init__(self, llm: LLMBase):
        self._llm = llm

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def analyze(
        self,
        evidence_refs: list[EvidenceReference],
    ) -> list[PaperKnowledge]:
        """Analyze evidence references and produce structured PaperKnowledge.

        Args:
            evidence_refs: List of EvidenceReference objects containing
                           excerpts from research papers.

        Returns:
            A list of PaperKnowledge objects, one per paper found in the
            evidence. Empty if analysis fails or no evidence is provided.
        """
        if not evidence_refs:
            logger.warning("Empty evidence_refs — skipping paper analysis")
            return []

        prompt = self._build_prompt(evidence_refs)
        try:
            resp = self._llm.generate(
                system_prompt=self._SYSTEM_PROMPT,
                user_message=prompt,
            )
            knowledge_list = self._parse_response(resp.text, evidence_refs)
            logger.info(
                "Analyzed %d paper knowledge entries from %d references",
                len(knowledge_list), len(evidence_refs),
            )
            return knowledge_list
        except Exception as e:
            logger.warning("Paper analysis failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    _SYSTEM_PROMPT = (
        "You are a paper analysis assistant. "
        "Organize the following evidence excerpts into structured per-paper knowledge. "
        "Each excerpt is from a research paper and contains information about the "
        "paper's architecture, training, datasets, benchmarks, or contributions.\n\n"
        "Return ONLY a JSON object keyed by paper_id. Each value is an object with:\n"
        '  "title": paper title (or "unknown"),\n'
        '  "problem_definition": the problem the paper addresses,\n'
        '  "motivation": why this work was done,\n'
        '  "main_contribution": the key contribution,\n'
        '  "architecture": {\n'
        '      "vision_encoder": "value or empty string",\n'
        '      "language_model": "value or empty string",\n'
        '      "connector": "value or empty string",\n'
        '      "fusion_method": "value or empty string",\n'
        '      "resolution_strategy": "value or empty string",\n'
        '  } or null,\n'
        '  "training": {\n'
        '      "pretraining_dataset": "value or empty string",\n'
        '      "instruction_dataset": "value or empty string",\n'
        '      "optimization_method": "value or empty string",\n'
        '      "loss_function": "value or empty string",\n'
        '      "training_stage": "value or empty string",\n'
        '  } or null,\n'
        '  "datasets": ["dataset_name_1", "dataset_name_2"],\n'
        '  "benchmark_references": ["benchmark_1", "benchmark_2"],\n'
        '  "limitations": "limitations mentioned or empty string",\n'
        '  "evidence_indices": [integer indices into the evidence list],\n\n'
        "IMPORTANT: Only extract information that is explicitly present in the "
        "evidence excerpts. Do NOT fabricate or generate new facts. "
        "If no information is found for a field, leave it as an empty string.\n\n"
        "Example:\n"
        '{\n'
        '  "paper123": {\n'
        '    "title": "Qwen2-VL: Better Vision-Language Model",\n'
        '    "problem_definition": "Vision-language model alignment",\n'
        '    "motivation": "Improve multimodal understanding",\n'
        '    "main_contribution": "Dynamic resolution approach",\n'
        '    "architecture": {\n'
        '      "vision_encoder": "ViT-L/14",\n'
        '      "language_model": "Qwen2-7B",\n'
        '      "connector": "MLP projector",\n'
        '      "fusion_method": "",\n'
        '      "resolution_strategy": "dynamic resolution"\n'
        '    },\n'
        '    "training": {\n'
        '      "pretraining_dataset": "LAION-5B",\n'
        '      "instruction_dataset": "LLaVA-Instruct-150K",\n'
        '      "optimization_method": "AdamW",\n'
        '      "loss_function": "",\n'
        '      "training_stage": ""\n'
        '    },\n'
        '    "datasets": ["ImageNet-1K"],\n'
        '    "benchmark_references": ["MMLU", "MathVista"],\n'
        '    "limitations": "Limited to English",\n'
        '    "evidence_indices": [0, 1, 2]\n'
        '  }\n'
        '}\n\n'
        "Return ONLY the JSON object. No markdown, no explanation."
    )

    def _build_prompt(self, evidence_refs: list[EvidenceReference]) -> str:
        lines = []
        for i, ref in enumerate(evidence_refs):
            lines.append(
                f"[{i}] paper_id={ref.paper_id} | section={ref.section} | "
                f"source_type={ref.source_type} | page={ref.page_number}\n"
                f"    excerpt: {ref.excerpt[:1000]}"
            )
        excerpts_text = "\n\n".join(lines)

        return (
            f"Organize the following evidence excerpts into structured "
            f"per-paper knowledge ({len(evidence_refs)} total):\n\n"
            f"{excerpts_text}"
        )

    def _parse_response(
        self,
        text: str,
        evidence_refs: list[EvidenceReference],
    ) -> list[PaperKnowledge]:
        """Parse LLM response into PaperKnowledge objects."""
        text = text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
            text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse paper analysis JSON")
            return []

        if not isinstance(data, dict):
            logger.warning("Paper analysis response is not a dict")
            return []

        knowledge_list: list[PaperKnowledge] = []
        for paper_id, paper_data in data.items():
            if not isinstance(paper_data, dict):
                continue

            # Resolve evidence indices to actual EvidenceReference objects
            evidence_indices = paper_data.get("evidence_indices", [])
            paper_evidence_refs: list[EvidenceReference] = []
            for idx in evidence_indices:
                if isinstance(idx, int) and 0 <= idx < len(evidence_refs):
                    paper_evidence_refs.append(evidence_refs[idx])

            # Build ArchitectureKnowledge
            arch_data = paper_data.get("architecture")
            architecture: Optional[ArchitectureKnowledge] = None
            if isinstance(arch_data, dict):
                architecture = ArchitectureKnowledge(
                    vision_encoder=KnowledgeField(
                        value=arch_data.get("vision_encoder", ""),
                        evidence_refs=list(paper_evidence_refs),
                    ),
                    language_model=KnowledgeField(
                        value=arch_data.get("language_model", ""),
                        evidence_refs=list(paper_evidence_refs),
                    ),
                    connector=KnowledgeField(
                        value=arch_data.get("connector", ""),
                        evidence_refs=list(paper_evidence_refs),
                    ),
                    fusion_method=KnowledgeField(
                        value=arch_data.get("fusion_method", ""),
                        evidence_refs=list(paper_evidence_refs),
                    ),
                    resolution_strategy=KnowledgeField(
                        value=arch_data.get("resolution_strategy", ""),
                        evidence_refs=list(paper_evidence_refs),
                    ),
                )

            # Build TrainingKnowledge
            training_data = paper_data.get("training")
            training: Optional[TrainingKnowledge] = None
            if isinstance(training_data, dict):
                training = TrainingKnowledge(
                    pretraining_dataset=KnowledgeField(
                        value=training_data.get("pretraining_dataset", ""),
                        evidence_refs=list(paper_evidence_refs),
                    ),
                    instruction_dataset=KnowledgeField(
                        value=training_data.get("instruction_dataset", ""),
                        evidence_refs=list(paper_evidence_refs),
                    ),
                    optimization_method=KnowledgeField(
                        value=training_data.get("optimization_method", ""),
                        evidence_refs=list(paper_evidence_refs),
                    ),
                    loss_function=KnowledgeField(
                        value=training_data.get("loss_function", ""),
                        evidence_refs=list(paper_evidence_refs),
                    ),
                    training_stage=KnowledgeField(
                        value=training_data.get("training_stage", ""),
                        evidence_refs=list(paper_evidence_refs),
                    ),
                )

            # Build datasets
            datasets_raw = paper_data.get("datasets", [])
            datasets: list[DatasetReference] = []
            if isinstance(datasets_raw, list):
                for ds_name in datasets_raw:
                    if isinstance(ds_name, str) and ds_name.strip():
                        datasets.append(DatasetReference(
                            name=ds_name.strip(),
                            evidence_refs=list(paper_evidence_refs),
                        ))

            # Build benchmark references
            benchmarks_raw = paper_data.get("benchmark_references", [])
            benchmark_references: list[str] = []
            if isinstance(benchmarks_raw, list):
                for b in benchmarks_raw:
                    if isinstance(b, str) and b.strip():
                        benchmark_references.append(b.strip())

            try:
                knowledge = PaperKnowledge(
                    paper_id=paper_id,
                    title=paper_data.get("title", ""),
                    problem_definition=paper_data.get("problem_definition", ""),
                    motivation=paper_data.get("motivation", ""),
                    main_contribution=paper_data.get("main_contribution", ""),
                    architecture=architecture,
                    training=training,
                    datasets=datasets,
                    benchmark_references=benchmark_references,
                    limitations=paper_data.get("limitations", ""),
                    evidence_refs=paper_evidence_refs,
                )
                knowledge_list.append(knowledge)
            except ValueError:
                continue

        return knowledge_list
