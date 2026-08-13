import json
import logging

from agent.core.llm import LLMBase
from agent.core.config import SearchConfig
from agent.tools.models import Paper
from agent.tools.prompts import RELEVANCE_JUDGE_PROMPT

logger = logging.getLogger(__name__)


class RelevanceFilter:
    """四层贡献类型过滤器（LLM 驱动）。

    过滤规则（Fix 3）：
    - contribution_type=strong → 保留
    - contribution_type=weak_extension → 保留
    - contribution_type=weak_application → 保留（跟踪 confidence）
    - contribution_type=irrelevant AND confidence >= 0.6 → 剔除
    - confidence < 0.6 → 降级为 weak_application，保留
    - 无摘要 → 强制 weak_application，confidence 上限 0.6
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
            rel = judgment.get("contribution_type", judgment.get("relevance", "weak_application"))
            conf = judgment.get("confidence", 0.0)
            reason = judgment.get("reason", "")

            p.relevance_confidence = conf
            p.relevance_reason = reason

            # 无摘要 → 强制 weak_application，confidence 上限 0.6
            if not p.abstract:
                rel = "weak_application"
                if conf > 0.6:
                    p.relevance_confidence = 0.6
                    conf = 0.6

            # 设置 contribution_type 和向后兼容的 relevance
            p.contribution_type = rel
            p.relevance = rel

            if rel == "irrelevant" and conf >= self.config.relevance_confidence_min:
                logger.warning("Filtered out: '%s' (confidence=%.2f, reason=%s)", p.title, conf, reason)
                continue

            if rel == "irrelevant" and conf < self.config.relevance_confidence_min:
                p.contribution_type = "weak_application"
                p.relevance = "weak"
                logger.info("Downgraded to weak_application (low confidence): '%s' (conf=%.2f)", p.title, conf)

            kept.append(p)

        strong = sum(1 for p in kept if p.contribution_type == "strong")
        ext = sum(1 for p in kept if p.contribution_type == "weak_extension")
        app = sum(1 for p in kept if p.contribution_type == "weak_application")
        filtered = len(papers) - len(kept)
        logger.info("Relevance: strong=%d, extension=%d, application=%d, filtered=%d (total=%d)",
                     strong, ext, app, filtered, len(papers))

        return kept

    @staticmethod
    def _parse_judgments(text: str) -> dict:
        try:
            data = json.loads(text)
            judgments = {}
            for j in data.get("judgments", []):
                title = (j.get("title") or "").lower().strip()
                if title:
                    # 优先读取 contribution_type，兼容旧版 relevance
                    rel = j.get("contribution_type", j.get("relevance", "weak_application"))
                    judgments[title] = {
                        "contribution_type": rel,
                        "confidence": float(j.get("confidence", 0.0)),
                        "reason": j.get("reason", ""),
                    }
            return judgments
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning("Failed to parse relevance judgments: %s", e)
            return {}