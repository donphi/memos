# ============================================================================
# FILE: router.py
# LOCATION: src/
# PIPELINE POSITION: Step 3 - Classifies incoming memos into category boxes
# PURPOSE: Deterministic hashtag routing with optional LLM fallback
# ============================================================================
"""
MODULE OVERVIEW:
Routes memos to category boxes. Hashtag matching is primary (deterministic).
LLM classification is fallback (opt-in via config). All tuneable values
come from Config — nothing hardcoded.

CLASSES:
- MemoRouter: Routes memos to categories

DEPENDENCIES:
- httpx==0.28.1 (via LLMProvider)
"""

import re
import logging
from typing import Optional
from src.config_loader import Config
from src.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class MemoRouter:
    """
    Routes memos to category boxes.

    Priority:
    1. Explicit hashtag (#box/category) -> deterministic
    2. Content scan for #box/ patterns -> deterministic (belt + suspenders)
    3. LLM classification -> non-deterministic fallback (if enabled)
    4. Default category or unrouted
    """

    def __init__(self, config: Config, llm: Optional[LLMProvider],
                 active_categories: list[dict]):
        self.config = config
        self.llm = llm
        self.tag_prefix = config.tag_prefix
        self.default_category = config.default_category
        self.enable_content_scan = config.enable_content_scan
        self.enable_llm = config.enable_llm_fallback
        self.ignore_tags = config.ignore_tags
        self.categories = {c["slug"]: c["description"] for c in active_categories}

    def update_categories(self, active_categories: list[dict]):
        self.categories = {c["slug"]: c["description"] for c in active_categories}
        logger.info(f"Router categories updated: {list(self.categories.keys())}")

    def route(self, content: str, tags: list[str]) -> tuple[Optional[str], str]:
        """
        Synchronous routing by hashtag. Returns (category_slug, routing_method).
        For LLM fallback, use route_async().
        """
        if any(t in self.ignore_tags for t in tags):
            return None, "ignored"

        category = self._route_by_hashtag(tags)
        if category:
            return category, "hashtag"

        if self.enable_content_scan:
            category = self._route_by_content_scan(content)
            if category:
                return category, "hashtag"

        return None, "unrouted"

    async def route_async(self, content: str, tags: list[str]) -> tuple[Optional[str], str]:
        """
        Full routing including async LLM fallback.
        """
        category, method = self.route(content, tags)
        if category:
            return category, method

        if self.enable_llm and self.llm:
            category = await self._route_by_llm(content)
            if category:
                return category, "llm"

        return self.default_category, "default"

    def _route_by_hashtag(self, tags: list[str]) -> Optional[str]:
        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower.startswith(self.tag_prefix):
                slug = tag_lower[len(self.tag_prefix):]
                if slug in self.categories:
                    return slug
                else:
                    logger.warning(
                        f"Tag #{self.tag_prefix}{slug} found but '{slug}' "
                        f"is not active. Known: {list(self.categories.keys())}"
                    )
        return None

    def _route_by_content_scan(self, content: str) -> Optional[str]:
        pattern = rf"#({re.escape(self.tag_prefix)})(\S+)"
        matches = re.findall(pattern, content, re.IGNORECASE)
        for _, slug in matches:
            slug_clean = slug.lower().rstrip(".,;:!?")
            if slug_clean in self.categories:
                return slug_clean
        return None

    async def _route_by_llm(self, content: str) -> Optional[str]:
        """
        LLM classification using prompt from config/prompts/classify.txt.
        All injectable variables are assembled here and passed centrally.
        """
        category_list = "\n".join(
            f"- {slug}: {desc}" for slug, desc in self.categories.items()
        )

        prompt = self.config.get_prompt("classify", {
            "categories": category_list,
            "content": content,
            "default_category": self.default_category,
        })

        result = await self.llm.complete(prompt, task="classify")
        if result:
            slug = result.strip().lower()
            if slug in self.categories:
                return slug
            logger.warning(f"LLM returned unknown category '{slug}'")
        return None