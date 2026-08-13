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

TASK: Judge whether each paper is relevant to the research topic: "{topic}"

RELEVANCE DEFINITION:
- STRONG relevant: The paper's primary contribution directly addresses the topic.
- WEAK relevant: The paper addresses the topic but not as primary contribution.
- IRRELEVANT: Completely different field or topic.

CONFIDENCE SCORE (0.0 to 1.0):
- 1.0: Absolutely certain
- 0.8-0.9: Very confident
- 0.6-0.7: Moderately confident
- 0.4-0.5: Weakly confident
- 0.0-0.3: Very uncertain

SPECIAL RULES:
- Papers WITHOUT an abstract CANNOT be "strong", confidence capped at 0.6.
- When in doubt, prefer keeping (weak + low confidence) over removing.

OUTPUT FORMAT: Return a JSON object:
{{
  "judgments": [
    {{"index": 1, "title": "Exact title", "relevance": "strong|weak|irrelevant",
     "confidence": 0.95, "reason": "Short justification"}}
  ]
}}
"""