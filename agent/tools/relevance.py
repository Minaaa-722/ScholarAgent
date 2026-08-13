import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Optional

from agent.core.llm import LLMBase
from agent.core.config import SearchConfig
from agent.tools.models import Paper
from agent.tools.prompts import (
    RELEVANCE_JUDGE_PROMPT,
    CONTRIBUTION_TYPES_DETAILED,
    CONTRIBUTION_TYPES_SIMPLE,
)

logger = logging.getLogger(__name__)


class RelevanceFilter:
    """LLM 驱动的论文相关性过滤器（含批量推理、缓存、预过滤、超时降级）。

    优化要点（2026-08 LLM 时延优化）：
    - 批量推理：每批最多 relevance_max_batch_size 篇，串行提交
    - 关键词预过滤：极宽松，仅剔除完全不沾边的论文
    - 硬性超时：超时论文标记为 unclassified，不阻塞 pipeline
    - 灰度开关 enable_detailed_contribution_classify：4 级 / 3 级
    - 进程内 FIFO 缓存（key=(doi, topic)）
    - 精简 prompt：reason 字段由 relevance_enable_reason 控制
    """

    def __init__(self, llm: LLMBase, config: SearchConfig):
        self.llm = llm
        self.config = config

        # 进程内 FIFO 缓存：{(doi, topic): judgment_dict}
        self._cache: dict[tuple[str, str], dict] = {}
        self._cache_keys: list[tuple[str, str]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def filter(self, papers: list[Paper], topic: str) -> list[Paper]:
        if not papers:
            return papers

        # Step 1: 关键词预过滤（极宽松，仅剔除完全不沾边的）
        if self.config.relevance_keyword_filter_enabled:
            papers, pre_filtered_count = self._keyword_prefilter(papers, topic)
            if pre_filtered_count > 0:
                logger.info(
                    "Keyword pre-filter removed %d clearly irrelevant papers, %d remain",
                    pre_filtered_count, len(papers),
                )

        # Step 2: 检查缓存，分离已缓存和未缓存的论文
        uncached, cached_judgments = self._check_cache(papers, topic)

        # Step 3: 分批 LLM 推理（串行，每批 max_batch_size 篇）
        batch_judgments = {}
        batches = self._chunk_papers(uncached, self.config.relevance_max_batch_size)

        for batch_idx, batch in enumerate(batches):
            logger.info(
                "LLM relevance batch %d/%d: %d papers",
                batch_idx + 1, len(batches), len(batch),
            )
            result = self._call_llm_batch(batch, topic)
            if result is None:
                # 超时或失败 → 该批全部标记为 unclassified
                fallback = self._unclassified_judgment()
                for p in batch:
                    batch_judgments[p.title.lower()] = fallback
            else:
                batch_judgments.update(result)
                self._update_cache(batch, result, topic)

        # 合并缓存 + 本次 LLM 结果
        all_judgments = {**cached_judgments, **batch_judgments}

        # Step 4: 应用分类规则
        kept = self._apply_judgments(papers, all_judgments)

        self._log_stats(papers, kept)
        return kept

    # ------------------------------------------------------------------
    # Step 1: Keyword pre-filter
    # ------------------------------------------------------------------

    @staticmethod
    def _keyword_prefilter(papers: list[Paper], topic: str) -> tuple[list[Paper], int]:
        """极宽松关键词预过滤。

        仅剔除标题+摘要完全不包含 topic 核心术语的论文。
        核心术语提取规则：
        - 将 topic 按空格/标点拆分为独立词
        - 过滤掉通用停用词（of, for, in, on, a, an, the, and, with, using, based）
        - 剩余词作为核心术语
        - 论文标题或摘要中只要包含任一核心术语（子串匹配），即保留
        """
        import re

        # 提取核心术语
        raw_terms = re.split(r'[\s,;:/()\[\]]+', topic.lower().strip())
        stop_words = {
            "of", "for", "in", "on", "a", "an", "the", "and", "with",
            "using", "based", "to", "from", "by", "at", "is", "are",
            "via", "toward", "towards", "their", "its", "our",
        }
        core_terms = [t for t in raw_terms if t and t not in stop_words and len(t) > 1]

        if not core_terms:
            return papers, 0  # 无可用的核心术语，全部保留

        removed = 0
        kept = []
        for p in papers:
            text = ((p.title or "") + " " + (p.abstract or "")).lower()
            if any(term in text for term in core_terms):
                kept.append(p)
            else:
                removed += 1
                logger.debug("Pre-filter removed: '%s' (no core term match)", p.title)

        return kept, removed

    # ------------------------------------------------------------------
    # Step 2: Cache check
    # ------------------------------------------------------------------

    def _check_cache(
        self, papers: list[Paper], topic: str,
    ) -> tuple[list[Paper], dict]:
        """分离已缓存和未缓存的论文。

        Returns:
            uncached: 需要调用 LLM 的论文列表
            cached_judgments: {title_lower: judgment_dict} 缓存命中结果
        """
        uncached = []
        cached_judgments = {}
        for p in papers:
            key = self._cache_key(p, topic)
            if key in self._cache:
                cached_judgments[p.title.lower()] = self._cache[key]
                logger.debug("Cache hit: '%s' (doi=%s)", p.title, p.doi)
            else:
                uncached.append(p)
        if cached_judgments:
            logger.info(
                "Cache: %d hits, %d uncached papers",
                len(cached_judgments), len(uncached),
            )
        return uncached, cached_judgments

    def _update_cache(self, papers: list[Paper], judgments: dict, topic: str) -> None:
        """将 LLM 结果写入 FIFO 缓存。"""
        max_size = self.config.relevance_cache_size
        for p in papers:
            key = self._cache_key(p, topic)
            if key is None:
                continue
            if key in self._cache:
                continue  # 已存在，不重复入队
            judgment = judgments.get(p.title.lower())
            if judgment is None:
                continue
            # FIFO 淘汰
            if len(self._cache_keys) >= max_size:
                oldest = self._cache_keys.pop(0)
                self._cache.pop(oldest, None)
            self._cache[key] = judgment
            self._cache_keys.append(key)

    @staticmethod
    def _cache_key(p: Paper, topic: str) -> Optional[tuple[str, str]]:
        """生成缓存 key：(doi, topic)。"""
        doi = (p.doi or "").strip().lower()
        if not doi:
            return None
        return (doi, topic.lower().strip())

    # ------------------------------------------------------------------
    # Step 3: Batch LLM calls
    # ------------------------------------------------------------------

    def _call_llm_batch(self, batch: list[Paper], topic: str) -> Optional[dict]:
        """对一批论文调用 LLM，返回 {title_lower: judgment}。

        超时或失败时返回 None → 调用方会标记为 unclassified。
        """
        # 构建 prompt
        include_reason = self.config.relevance_enable_reason
        if self.config.enable_detailed_contribution_classify:
            contribution_types = CONTRIBUTION_TYPES_DETAILED
        else:
            contribution_types = CONTRIBUTION_TYPES_SIMPLE

        reason_field = ', "reason": "Short justification"' if include_reason else ""
        prompt = RELEVANCE_JUDGE_PROMPT.format(
            topic=topic,
            contribution_types=contribution_types,
            reason_field=reason_field,
        )

        # 构建论文列表
        paper_list = []
        for i, p in enumerate(batch, 1):
            abstract = (p.abstract or "")[:300]
            paper_list.append({"index": i, "title": p.title, "abstract": abstract})
        user_msg = json.dumps(paper_list, ensure_ascii=False)

        # 带超时的 LLM 调用
        timeout = self.config.relevance_llm_timeout
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.llm.generate, prompt, user_msg)
                resp = future.result(timeout=timeout)
        except TimeoutError:
            logger.warning(
                "LLM batch timed out after %ds (%d papers) — marking as unclassified",
                timeout, len(batch),
            )
            return None
        except Exception as e:
            logger.warning(
                "LLM batch failed: %s (%d papers) — marking as unclassified",
                e, len(batch),
            )
            return None

        # 解析结果
        judgments = self._parse_judgments(resp.text)
        if not judgments:
            logger.warning(
                "LLM batch returned empty/unparseable judgments — marking as unclassified",
            )
            return None

        return judgments

    @staticmethod
    def _chunk_papers(papers: list[Paper], chunk_size: int) -> list[list[Paper]]:
        """将论文列表按 chunk_size 切分为多个子列表。"""
        return [papers[i:i + chunk_size] for i in range(0, len(papers), chunk_size)]

    # ------------------------------------------------------------------
    # Step 4: Apply judgments
    # ------------------------------------------------------------------

    def _apply_judgments(
        self, papers: list[Paper], all_judgments: dict,
    ) -> list[Paper]:
        """将判断结果应用到每篇论文，执行过滤规则。"""
        kept = []

        for p in papers:
            judgment = all_judgments.get(p.title.lower(), {})
            rel = judgment.get(
                "contribution_type",
                judgment.get("relevance", "weak_application"),
            )
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

            # 过滤规则
            if rel == "irrelevant" and conf >= self.config.relevance_confidence_min:
                logger.warning(
                    "Filtered out: '%s' (confidence=%.2f, reason=%s)",
                    p.title, conf, reason,
                )
                continue

            if rel == "irrelevant" and conf < self.config.relevance_confidence_min:
                p.contribution_type = "weak_application"
                p.relevance = "weak"
                logger.info(
                    "Downgraded to weak_application (low confidence): '%s' (conf=%.2f)",
                    p.title, conf,
                )

            # unclassified 标记：保持默认 weak_application，confidence=0.5
            if rel == "unclassified":
                p.contribution_type = "weak_application"
                p.relevance = "weak"
                p.relevance_confidence = 0.5
                logger.info("Unclassified paper kept as weak_application: '%s'", p.title)

            kept.append(p)

        return kept

    @staticmethod
    def _unclassified_judgment() -> dict:
        """超时/失败时的默认判断。"""
        return {
            "contribution_type": "unclassified",
            "confidence": 0.5,
            "reason": "LLM timeout or failure — unclassified",
        }

    def _log_stats(self, papers: list[Paper], kept: list[Paper]) -> None:
        """输出过滤统计日志。"""
        total = len(papers)
        filtered = total - len(kept)

        if self.config.enable_detailed_contribution_classify:
            strong = sum(1 for p in kept if p.contribution_type == "strong")
            ext = sum(1 for p in kept if p.contribution_type == "weak_extension")
            app = sum(1 for p in kept if p.contribution_type == "weak_application")
            unc = sum(1 for p in kept if p.contribution_type == "unclassified")
            logger.info(
                "Relevance: strong=%d, extension=%d, application=%d, "
                "unclassified=%d, filtered=%d (total=%d)",
                strong, ext, app, unc, filtered, total,
            )
        else:
            rel = sum(1 for p in kept if p.contribution_type == "relevant")
            weak = sum(1 for p in kept if p.contribution_type == "weak")
            unc = sum(1 for p in kept if p.contribution_type == "unclassified")
            logger.info(
                "Relevance: relevant=%d, weak=%d, unclassified=%d, filtered=%d (total=%d)",
                rel, weak, unc, filtered, total,
            )

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_judgments(text: str) -> dict:
        """解析 LLM 返回的 JSON 判断结果。"""
        try:
            data = json.loads(text)
            judgments = {}
            for j in data.get("judgments", []):
                title = (j.get("title") or "").lower().strip()
                if title:
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
