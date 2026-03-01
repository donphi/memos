# ============================================================================
# FILE: category_sync.py
# LOCATION: src/
# PIPELINE POSITION: Step 1 - Syncs category memo -> database categories table
# PURPOSE: Keep the categories table in sync with the pinned category memo
# ============================================================================
"""
MODULE OVERVIEW:
When the category memo is created or updated (detected via webhook or on startup),
this module reads the memo content, diffs it against the current categories table,
and applies additions, soft-deletes, and description updates.

CLASSES:
- CategorySync: Reads category memo, reconciles with DB

METHODS:
- sync(): Full reconciliation of memo content -> categories table
- get_active_categories(): Return current active categories from DB

HYPERPARAMETERS:
- N/A

DEPENDENCIES:
- sqlalchemy==2.0.36
"""

import json
import logging
from sqlalchemy.orm import Session
from src.models import Category

logger = logging.getLogger(__name__)


class CategorySync:
    """
    Reconciles the category memo content with the database categories table.

    Why reconcile instead of overwrite: If you delete a category from the memo,
    existing memos already routed to that category shouldn't lose their routing.
    We soft-delete (is_active=False) so historical data stays intact.
    """

    def __init__(self, session_factory):
        self.session_factory = session_factory

    def sync(self, categories_from_memo: list[dict]) -> dict:
        """
        Sync category definitions from the pinned memo into the database.

        Process:
        1. Read current categories from DB
        2. Determine additions (in memo but not in DB)
        3. Determine reactivations (in memo and in DB but inactive)
        4. Determine soft-deletes (in DB but not in memo)
        5. Update descriptions for existing active categories
        6. Apply all changes in one transaction

        Args:
            categories_from_memo: List of {"slug": "...", "description": "..."}

        Returns:
            Summary dict: {"added": [...], "reactivated": [...],
                          "deactivated": [...], "updated": [...]}
        """
        session: Session = self.session_factory()
        try:
            memo_slugs = {c["slug"] for c in categories_from_memo}
            memo_lookup = {c["slug"]: c["description"] for c in categories_from_memo}

            existing = session.query(Category).all()
            existing_lookup = {c.slug: c for c in existing}
            existing_slugs = set(existing_lookup.keys())

            result = {"added": [], "reactivated": [], "deactivated": [], "updated": []}

            # New categories
            for slug in memo_slugs - existing_slugs:
                cat = Category(
                    slug=slug,
                    description=memo_lookup[slug],
                    is_active=True,
                )
                session.add(cat)
                result["added"].append(slug)

            # Existing categories - check for changes
            for slug in memo_slugs & existing_slugs:
                cat = existing_lookup[slug]
                if not cat.is_active:
                    cat.is_active = True
                    result["reactivated"].append(slug)
                if cat.description != memo_lookup[slug]:
                    cat.description = memo_lookup[slug]
                    result["updated"].append(slug)

            # Categories removed from memo - soft delete
            for slug in existing_slugs - memo_slugs:
                cat = existing_lookup[slug]
                if cat.is_active:
                    cat.is_active = False
                    result["deactivated"].append(slug)

            session.commit()
            logger.info(f"Category sync complete: {result}")
            return result

        except Exception as e:
            session.rollback()
            logger.error(f"Category sync failed: {e}")
            raise
        finally:
            session.close()

    def get_active_categories(self) -> list[dict]:
        """
        Return all active categories from the database.

        Returns:
            List of {"slug": "...", "description": "..."}
        """
        session = self.session_factory()
        try:
            cats = session.query(Category).filter(
                Category.is_active == True
            ).order_by(Category.slug).all()
            return [{"slug": c.slug, "description": c.description} for c in cats]
        finally:
            session.close()