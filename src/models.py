# ============================================================================
# FILE: models.py
# LOCATION: src/
# PIPELINE POSITION: Data layer - schema for immutable event log + categories
# PURPOSE: SQLAlchemy models for event sourcing and category state
# ============================================================================
"""
MODULE OVERVIEW:
Defines the database schema for the routing service. Two core concerns:
1. Category registry (synced from the pinned category memo)
2. Immutable event log (every memo create/update/delete is recorded with diffs)

CLASSES:
- Category: Current state of routing categories
- MemoEvent: Append-only event log with content snapshots and diffs
- MemoRouting: Which box a memo was routed to (and why)

TABLES:
- categories: Managed list of box categories
- memo_events: Immutable append-only log of all memo changes
- memo_routings: Current box assignment per memo

HYPERPARAMETERS:
- N/A (schema definition, no tunable values)

DEPENDENCIES:
- sqlalchemy==2.0.36
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, DateTime, Boolean, Integer,
    ForeignKey, Index, create_engine, event,
)
from sqlalchemy.orm import declarative_base, relationship, Session

Base = declarative_base()


class Category(Base):
    """
    A routing category (box) synced from the pinned category memo.

    Why a separate table instead of just reading the memo each time:
    1. Fast lookups during webhook processing (no API call needed)
    2. Tracks when categories were added/removed/renamed
    3. Survives if the category memo is temporarily unavailable
    """
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, default="")
    is_active = Column(Boolean, default=True)  # Soft delete - never hard delete

    # Audit fields
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Category slug={self.slug} active={self.is_active}>"


class MemoEvent(Base):
    """
    Immutable append-only log of every memo change.

    Why immutable/append-only:
    - Full audit trail: you can reconstruct any memo's state at any point
    - Undo capability: revert to any previous snapshot
    - Diff tracking: see exactly what changed between versions

    Design: Each row is a snapshot. The diff field stores the delta from
    the previous event for the same memo. Content stores the full state
    so you never need to replay diffs to reconstruct.
    """
    __tablename__ = "memo_events"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Memo identity (Memos UID is stable across DB migrations)
    memo_uid = Column(String(100), nullable=False, index=True)

    # Event type: "created", "updated", "deleted"
    event_type = Column(String(20), nullable=False)

    # Full content snapshot at this point in time
    content_snapshot = Column(Text, nullable=False, default="")

    # Diff from previous version (empty for "created" events)
    # Stored as unified diff format
    content_diff = Column(Text, default="")

    # Tags at this point in time (JSON array as string)
    tags_snapshot = Column(Text, default="[]")

    # Which category was this routed to (null if unrouted)
    routed_to = Column(String(100), ForeignKey("categories.slug"), nullable=True)

    # How was routing decided: "hashtag", "llm", "manual", "unrouted"
    routing_method = Column(String(20), default="unrouted")

    # Timestamp from Memos (when the memo was actually changed)
    memo_timestamp = Column(String(50), default="")

    # Timestamp when we received and logged this event
    logged_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        # Fast lookup: all events for a memo, in order
        Index("ix_memo_events_uid_logged", "memo_uid", "logged_at"),
    )

    def __repr__(self):
        return f"<MemoEvent uid={self.memo_uid} type={self.event_type} routed={self.routed_to}>"


class MemoRouting(Base):
    """
    Current box assignment for each memo (mutable - updates on re-routing).

    Why separate from MemoEvent:
    - MemoEvent is immutable (append-only history)
    - MemoRouting is the current state (fast lookups for "what's in box X?")
    - This is a materialized view of the latest routing decision
    """
    __tablename__ = "memo_routings"

    memo_uid = Column(String(100), primary_key=True)
    category_slug = Column(String(100), ForeignKey("categories.slug"), nullable=True)
    routing_method = Column(String(20), default="unrouted")
    last_content_preview = Column(Text, default="")  # First 200 chars for quick display
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<MemoRouting uid={self.memo_uid} -> {self.category_slug}>"


# ---- Database initialization ----

def init_db(database_url: str, echo: bool = False) -> Session:
    """
    Create tables and return a session factory.
    echo parameter comes from tuning.yaml database.echo.
    """
    engine = create_engine(database_url, echo=echo)
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(bind=engine)