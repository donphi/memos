# ============================================================================
# FILE: event_logger.py
# LOCATION: src/
# PIPELINE POSITION: Step 2 - Logs every memo change as an immutable event
# PURPOSE: Append-only event log with content snapshots and unified diffs
# ============================================================================
"""
MODULE OVERVIEW:
Every memo create/update/delete received via webhook gets logged here as an
immutable event. Each event stores the full content snapshot AND the diff
from the previous version, so you can reconstruct state at any point or
undo changes by reverting to a previous snapshot.

CLASSES:
- EventLogger: Writes immutable events to the memo_events table

METHODS:
- log_event(): Record a memo change with snapshot and diff
- get_memo_history(): Retrieve all events for a memo in order
- get_latest_snapshot(): Get the most recent content for a memo

HYPERPARAMETERS:
- PREVIEW_LENGTH: 200 (location: _make_preview, purpose: truncation for quick display)

DEPENDENCIES:
- sqlalchemy==2.0.36
"""

import json
import difflib
import logging
from typing import Optional
from sqlalchemy.orm import Session
from src.models import MemoEvent, MemoRouting

logger = logging.getLogger(__name__)

class EventLogger:
    """
    Append-only event log for memo changes.

    Why full snapshots AND diffs:
    - Snapshots: Fast reconstruction without replaying history
    - Diffs: See exactly what changed, useful for LLM action generation
    - Both: Belt and suspenders. Storage is cheap, data loss isn't.
    """

    def __init__(self, session_factory, preview_length: int = None):
        """
        Args:
            session_factory: SQLAlchemy session factory
            preview_length: Characters of content preview for routing table.
                            Must be provided from tuning.yaml events.preview_length.
        """
        if preview_length is None:
            raise ValueError(
                "preview_length is required — pass from tuning.yaml events.preview_length"
            )
        self.session_factory = session_factory
        self.preview_length = preview_length

    def log_event(
        self,
        memo_uid: str,
        event_type: str,
        content: str,
        tags: list[str],
        routed_to: Optional[str],
        routing_method: str,
        memo_timestamp: str = "",
    ) -> MemoEvent:
        """
        Record an immutable event for a memo change.

        Process:
        1. Fetch previous snapshot for this memo (if exists)
        2. Compute unified diff between previous and current content
        3. Insert new event row (never update, never delete)
        4. Update the mutable routing table with current state

        Args:
            memo_uid: Memos UID of the changed memo
            event_type: "created", "updated", or "deleted"
            content: Full current content of the memo
            tags: List of tag strings extracted from the memo
            routed_to: Category slug this memo was routed to (or None)
            routing_method: How routing was decided ("hashtag", "llm", "unrouted")
            memo_timestamp: When the change happened in Memos

        Returns:
            The created MemoEvent record
        """
        session: Session = self.session_factory()
        try:
            # Get previous snapshot for diff computation
            previous = self._get_latest_event(session, memo_uid)
            previous_content = previous.content_snapshot if previous else ""

            # Compute unified diff
            diff = self._compute_diff(previous_content, content, memo_uid)

            # Create immutable event
            evt = MemoEvent(
                memo_uid=memo_uid,
                event_type=event_type,
                content_snapshot=content,
                content_diff=diff,
                tags_snapshot=json.dumps(tags),
                routed_to=routed_to,
                routing_method=routing_method,
                memo_timestamp=memo_timestamp,
            )
            session.add(evt)

            # Update mutable routing table (current state)
            self._update_routing(session, memo_uid, routed_to, routing_method, content)

            session.commit()
            logger.info(
                f"Logged {event_type} event for memo {memo_uid} "
                f"-> {routed_to or 'unrouted'} ({routing_method})"
            )
            return evt

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to log event for {memo_uid}: {e}")
            raise
        finally:
            session.close()

    def get_memo_history(self, memo_uid: str) -> list[dict]:
        """
        Retrieve all events for a memo, oldest first.

        Returns:
            List of event dicts with snapshot, diff, routing info
        """
        session = self.session_factory()
        try:
            events = (
                session.query(MemoEvent)
                .filter(MemoEvent.memo_uid == memo_uid)
                .order_by(MemoEvent.logged_at.asc())
                .all()
            )
            return [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "content_snapshot": e.content_snapshot,
                    "content_diff": e.content_diff,
                    "tags": json.loads(e.tags_snapshot),
                    "routed_to": e.routed_to,
                    "routing_method": e.routing_method,
                    "memo_timestamp": e.memo_timestamp,
                    "logged_at": e.logged_at.isoformat() if e.logged_at else "",
                }
                for e in events
            ]
        finally:
            session.close()

    def get_recently_routed(self, category_slug: str, limit: int = None) -> list[dict]:
        """
        Get the most recent memos routed to a specific box.

        Why this exists: The LLM action generator needs to read "what's new
        in box X" to update the action file.
        """
        effective_limit = limit if limit is not None else 20
        session = self.session_factory()
        try:
            routings = (
                session.query(MemoRouting)
                .filter(MemoRouting.category_slug == category_slug)
                .order_by(MemoRouting.updated_at.desc())
                .limit(effective_limit)
                .all()
            )
            return [
                {
                    "memo_uid": r.memo_uid,
                    "category_slug": r.category_slug,
                    "preview": r.last_content_preview,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else "",
                }
                for r in routings
            ]
        finally:
            session.close()

    # ---- Internal helpers ----

    def _get_latest_event(self, session: Session, memo_uid: str) -> Optional[MemoEvent]:
        """Get the most recent event for a memo."""
        return (
            session.query(MemoEvent)
            .filter(MemoEvent.memo_uid == memo_uid)
            .order_by(MemoEvent.logged_at.desc())
            .first()
        )

    def _compute_diff(self, old_content: str, new_content: str, label: str) -> str:
        """
        Compute unified diff between two content versions.

        Why unified diff: Human-readable, standard format, parseable by tools.
        """
        if not old_content:
            return ""  # No diff for first version

        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"{label} (previous)",
            tofile=f"{label} (current)",
        )
        return "".join(diff)

    def _update_routing(
        self, session: Session, memo_uid: str,
        category_slug: Optional[str], routing_method: str, content: str
    ):
        """Update the mutable routing table with current state."""
        routing = session.query(MemoRouting).filter(
            MemoRouting.memo_uid == memo_uid
        ).first()

        preview = content[:self.preview_length] if content else ""

        if routing:
            routing.category_slug = category_slug
            routing.routing_method = routing_method
            routing.last_content_preview = preview
        else:
            routing = MemoRouting(
                memo_uid=memo_uid,
                category_slug=category_slug,
                routing_method=routing_method,
                last_content_preview=preview,
            )
            session.add(routing)

