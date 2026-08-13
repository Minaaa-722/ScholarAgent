METHODOLOGY_QUERY_PROMPT = """\
You are a research methodology search query generator for academic paper retrieval.

TASK: Generate exactly 5 search queries to find **core methodological innovation papers**
for a survey on "{topic}".

CRITICAL RULES:
- Each query MUST target a **method category / design space / technique family**
  — NOT a specific model name, NOT a downstream application
- AVOID: "for X", "in X", "using X for Y", "X-based", "application of X to Y"
- PREFER: general mechanism categories like "X variants", "X design space",
  "X mechanism", "efficient X", "X architecture design", "X formulation"
- Output BOTH a broad method category AND a focused variant on each line,
  separated by " -> "
  Example: "attention mechanism design -> attention mechanism"
  → This will be expanded into two separate queries
- NO generic words: deep learning, survey, review, advances, recent, trends
- NO conversational text, NO numbering, NO explanation, NO markdown
- Be specific about the methodology dimension

OUTPUT FORMAT (exactly one pair per line):
method category -> focused variant
method category -> focused variant
...

Example for topic="Efficient Transformer":
attention mechanism optimization -> attention optimization
position encoding design -> position encoding
model compression technique -> model compression
architectural search space -> neural architecture search
training efficiency method -> training efficiency
"""


SEARCH_QUERY_PROMPT = """\
You are a literature search query generator for academic paper retrieval.

TASK: Generate exactly 5 search queries to find academic papers for a survey paper.

CRITICAL RULES:
- Each query MUST be a specific technique / method / model / approach name
- Output BOTH full name AND common abbreviation on each line, separated by " -> "
  Example: "Vision Transformer -> ViT"
  → This will be expanded into two separate queries: "Vision Transformer" AND "ViT"
- NO generic words: deep learning, survey, review, advances, recent, progress, trends, challenges
- NO conversational text, NO numbering, NO explanation, NO markdown
- Be specific: use concrete method names
- Each line must be one "full name -> abbreviation" pair

OUTPUT FORMAT (exactly one pair per line, no blank lines):
full technical name -> abbreviation
full technical name -> abbreviation
...

Example for topic="Efficient Transformer":
attention mechanism optimization -> attention optimization
model quantization -> quantization
knowledge distillation -> knowledge distillation
mixture of experts -> MoE
speculative decoding -> speculative decoding
"""


RELEVANCE_JUDGE_PROMPT = """\
You are a strict relevance judge for academic literature search.

TASK: For each paper, determine its contribution type relative to the
research topic: "{topic}"

CONTRIBUTION TYPES:
- strong: The paper's PRIMARY contribution is a core METHODOLOGICAL INNOVATION
  directly addressing the topic. The paper proposes, analyzes, or fundamentally
  improves the method ITSELF. Examples: a new attention mechanism variant,
  a novel position encoding scheme, a theoretical analysis of the method.
  → HIGH VALUE for survey — keep unconditionally.

- weak_extension: The paper's primary contribution is an EXTENSION or
  IMPROVEMENT of an existing method applied to a domain task. The method
  innovation is real but not the main claim. Examples: adapting a method
  to a new modality with architectural modifications, improving efficiency
  for a specific use case.
  → MODERATE VALUE for survey — keep.

- weak_application: The paper uses the target method primarily as a TOOL
  or COMPONENT within a larger system applied to a DOWNSTREAM TASK. The
  paper's contribution is in the application, not the method itself.
  Examples: "X for image classification", "X-based Y detection system",
  "applying X to Z problem".
  → LOW VALUE for survey — keep only if confidence is high.

- irrelevant: The paper does not address the topic or addresses it only
  in passing. Completely different field or topic.
  → REMOVE if confidence >= 0.6.

CONFIDENCE SCORE (0.0 to 1.0):
- 1.0: Absolutely certain
- 0.8-0.9: Very confident
- 0.6-0.7: Moderately confident
- 0.4-0.5: Weakly confident
- 0.0-0.3: Very uncertain

SPECIAL RULES:
- Papers WITHOUT an abstract: default to weak_application, confidence capped at 0.6.
- When in doubt between strong and weak_extension, prefer weak_extension.
- When in doubt between weak_extension and weak_application, prefer weak_extension.
- weak_application with confidence < 0.6: downgrade to irrelevant and remove.

OUTPUT FORMAT: Return a JSON object:
{{
  "judgments": [
    {{"index": 1, "title": "Exact title",
      "contribution_type": "strong|weak_extension|weak_application|irrelevant",
      "confidence": 0.95, "reason": "Short justification"}}
  ]
}}
"""