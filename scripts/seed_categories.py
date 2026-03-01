#!/usr/bin/env python3
# ============================================================================
# FILE: seed_categories.py
# LOCATION: scripts/
# PURPOSE: Creates the pinned category memo on a fresh Memos instance
# ============================================================================
"""
Run this once after first deploy to create the category registry memo.
It will print the memo UID which you then add to your .env file.

Usage:
    python scripts/seed_categories.py

Or from Docker:
    docker compose exec api python scripts/seed_categories.py
"""

import os
import asyncio
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config_loader import Config
from src.memos_adapter import MemosAdapter

DEFAULT_CATEGORIES = """# Categories
# Edit this memo to add, remove, or rename categories.
# Format: - slug: Description of what goes in this box
# The routing service watches this memo and syncs automatically.

- inbox: Default landing box for unclassified memos
- health: Medical appointments, fitness, body, transplant follow-ups
- work: Career, job search, applications, professional development
- finance: Money, debt, budget, investments
- project/dissertation: Luddite Loop, academic work, research
- personal: Relationships, home, life admin
- tech: Hardware, software, system administration, dev environment
- learning: Courses, reading, skill development
"""


async def main():
    config = Config.load()

    base_url = os.environ.get("MEMOS_BASE_URL", config.memos_base_url)
    api_token = os.environ.get("MEMOS_API_TOKEN", config.memos_api_token)

    if not api_token:
        print("Set MEMOS_API_TOKEN environment variable first")
        print("   Create one in Memos: Settings > Access Tokens")
        sys.exit(1)

    adapter = MemosAdapter(
        base_url, api_token,
        api_version=config.memos_api_version,
        request_timeout=config.memos_request_timeout,
    )

    try:
        print(f"Connecting to Memos at {base_url}")
        memo = await adapter.create_memo(
            content=DEFAULT_CATEGORIES,
            visibility="PRIVATE",
        )

        webhook_url = config.memos_webhook_url

        print(f"Category memo created!")
        print(f"")
        print(f"   UID: {memo['uid']}")
        print(f"   Name: {memo['name']}")
        print(f"")
        print(f"   Next steps:")
        print(f"   1. Add this to your .env file:")
        print(f"      CATEGORY_MEMO_UID={memo['uid']}")
        print(f"   2. Pin this memo in the Memos UI so it stays visible")
        print(f"   3. Set up the webhook in Memos:")
        print(f"      Settings > Webhooks > Add")
        print(f"      URL: {webhook_url}")
        print(f"   4. Install the category dropdown JS into Memos")
        print(f"   5. Restart the router: docker compose restart api")

    except Exception as e:
        print(f"Failed to create category memo: {e}")
        sys.exit(1)
    finally:
        await adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
