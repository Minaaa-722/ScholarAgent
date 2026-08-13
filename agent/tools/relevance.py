import json
import logging

from agent.core.llm import LLMBase
from agent.core.config import SearchConfig
from agent.tools.models import Paper
from agent.tools.prompts import RELEVANCE_JUDGE_PROMPT

logger = logging.getLogger(__name__)


class RelevanceFilter:
    """三级相关性过滤器（LLM 驱动）。

    过滤规则（Fix 3）：
    - relevance=strong → 保留
    - relevance=weak → 保留
    - relevance=irrelevant AND confidence >= 0.6 → 剔除
    - confidence < 0.6 → 标记为 weak，保留，禁止删除
    """

    def __init__(self, llm: LLMBase, config: SearchConfig):
        self.llm = llm
        self.config = config

    def filter(self, papers: list[Paper], topic: str) -> list[Paper]:
        if not papers:
            return papers

        prompt = RELEVANCE_JUDGE_PROMPT.format(topic=topic)
        paper_list = []
        for i, p in enumerate(papers, 1):
            abstract = (p.abstract or "")[:300]
            paper_list.append({"index": i, "title": p.title, "abstract": abstract})

        user_msg = json.dumps(paper_list, ensure_ascii=False)
        resp = self.llm.generate(prompt, user_msg)
        judgments = self._parse_judgments(resp.text)

        kept = []
        for p in papers:
            judgment = judgments.get(p.title.lower(), {})
            rel = judgment.get("relevance", "weak")
            conf = judgment.get("confidence", 0.0)
            reason = judgment.get("reason", "")

            p.relevance = rel
            p.relevance_confidence = conf
            p.relevance_reason = reason

            # 无摘要 → confidence 上限 0.6
            if not p.abstract and conf > 0.6:
                p.relevance_confidence = 0.6
                conf = 0.6

            # 无摘要 → 不可为 strong
            if not p.abstract and p.relevance == "strong":
                p.relevance = "weak"

            if rel == "irrelevant" and conf >= self.config.relevance_confidence_min:
                logger.warning("Filtered out: '%s' (confidence=%.2f, reason=%s)", p.title, conf, reason)
                continue

            if rel == "irrelevant" and conf < self.config.relevance_confidence_min:
                p.relevance = "weak"
                logger.info("Downgraded to weak (low confidence): '%s' (conf=%.2f)", p.title, conf)

            kept.append(p)

        strong = sum(1 for p in kept if p.relevance == "strong")
        weak = sum(1 for p in kept if p.relevance == "weak")
        filtered = len(papers) - len(kept)
        logger.info("Relevance: strong=%d, weak=%d, filtered=%d (total=%d)", strong, weak, filtered, len(papers))

        return kept

    @staticmethod
    def _parse_judgments(text: str) -> dict:
        try:
            data = json.loads(text)
            judgments = {}
            for j in data.get("judgments", []):
                title = (j.get("title") or "").lower().strip()
                if title:
                    judgments[title] = {
                        "relevance": j.get("relevance", "weak"),
                        "confidence": float(j.get("confidence", 0.0)),
                        "reason": j.get("reason", ""),
                    }
            return judgments
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning("Failed to parse relevance judgments: %s", e)
            return {}