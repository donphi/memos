# ============================================================================
# FILE: memos_adapter.py
# LOCATION: src/
# PIPELINE POSITION: Foundation layer - all Memos API access flows through here
# PURPOSE: Isolate Memos API version specifics so upgrades only touch this file
# ============================================================================
"""
MODULE OVERVIEW:
Thin adapter that wraps the Memos REST API. Every other module in this project
talks to Memos ONLY through this adapter. When Memos releases a breaking API
change (which happens frequently), you update this file and nothing else.

CLASSES:
- MemosAdapter: Async client for Memos API operations

METHODS:
- get_memo(): Fetch a single memo by UID
- list_memos_metadata(): Fetch all memos with metadata only (for tag extraction)
- create_memo(): Create a new memo
- update_memo(): Update existing memo content
- get_category_memo(): Fetch the pinned category registry memo
- extract_tags(): Parse tags from a memo's property field

HYPERPARAMETERS:
- All from config YAML files via Config. api_version and request_timeout passed to constructor.
- METADATA_VIEW: Fixed Memos API enum (protocol constant, not tuneable)

DEPENDENCIES:
- httpx==0.28.1
"""

import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Hyperparameters
# Memos API enum — not tuneable, this is a fixed protocol value
METADATA_VIEW = "MEMO_VIEW_METADATA_ONLY"  # Lightweight fetch - tags only, no content


class MemosAdapter:
    """
    Async adapter for the Memos REST API.

    Why this exists: Memos breaks its API between minor versions. By funneling
    all API access through one class, a version upgrade means editing one file
    instead of hunting through the entire codebase.

    The adapter translates between Memos' internal data shapes and our own
    domain objects (plain dicts with stable keys). Downstream code never sees
    Memos-specific field names.
    """

    def __init__(self, base_url: str, api_token: str,
                 api_version: str = None, request_timeout: float = None):
        """
        Args:
            base_url: Memos server URL (e.g. http://memos:5230)
            api_token: Bearer token from Memos Settings > Access Tokens
            api_version: API version path segment (from paths.yaml memos.api_version)
            request_timeout: Seconds before API calls fail (from tuning.yaml memos.request_timeout_seconds)

        Note: api_version and request_timeout have no hardcoded defaults.
        They must be provided by the caller (server.py reads them from Config).
        """
        if api_version is None or request_timeout is None:
            raise ValueError(
                "api_version and request_timeout are required — "
                "pass them from config YAML files via Config"
            )
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }
        self.client = httpx.AsyncClient(
            base_url=f"{self.base_url}/api/{api_version}",
            headers=self.headers,
            timeout=request_timeout,
        )

    # ---- Core CRUD ----

    async def get_memo(self, memo_uid: str) -> Optional[dict]:
        """
        Fetch a single memo by its UID.

        Returns:
            Normalized dict with keys: uid, content, tags, pinned, created, updated
            None if not found.

        Why UID not ID: Memos uses both numeric IDs and string UIDs.
        UIDs are stable across database migrations; numeric IDs are not.
        """
        try:
            # Memos v0.24.x uses /memos/{name} where name = "memos/{uid}"
            resp = await self.client.get(f"/memos/{memo_uid}")
            resp.raise_for_status()
            return self._normalize_memo(resp.json())
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        except Exception as e:
            logger.error(f"Failed to fetch memo {memo_uid}: {e}")
            raise

    async def list_memos_metadata(self, creator_filter: Optional[str] = None) -> list[dict]:
        """
        Fetch all memos with metadata only (tags, properties, no full content).

        Why metadata view: Fetching full content for every memo to extract tags
        is wasteful. The metadata view returns property.tags without the body.

        Args:
            creator_filter: Optional user filter like "users/1"

        Returns:
            List of normalized memo dicts (uid, tags, pinned, created, updated)
        """
        params = {"view": METADATA_VIEW}
        if creator_filter:
            params["filter"] = f"creator == '{creator_filter}'"

        all_memos = []
        page_token = None

        while True:
            if page_token:
                params["pageToken"] = page_token

            resp = await self.client.get("/memos", params=params)
            resp.raise_for_status()
            data = resp.json()

            for memo in data.get("memos", []):
                all_memos.append(self._normalize_memo(memo))

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return all_memos

    async def create_memo(self, content: str, visibility: str = "PRIVATE") -> dict:
        """
        Create a new memo.

        Args:
            content: Markdown content string
            visibility: "PRIVATE", "PROTECTED", or "PUBLIC"

        Returns:
            Normalized memo dict of the created memo
        """
        payload = {"content": content, "visibility": visibility}
        resp = await self.client.post("/memos", json=payload)
        resp.raise_for_status()
        return self._normalize_memo(resp.json())

    async def update_memo(self, memo_name: str, content: str) -> dict:
        """
        Update an existing memo's content.

        Args:
            memo_name: The memo resource name (e.g. "memos/abc123")
            content: New markdown content

        Returns:
            Normalized memo dict
        """
        payload = {"content": content}
        params = {"updateMask": "content"}
        resp = await self.client.patch(
            f"/{memo_name}",
            json=payload,
            params=params,
        )
        resp.raise_for_status()
        return self._normalize_memo(resp.json())

    # ---- Category-specific ----

    async def get_category_memo(self, category_memo_uid: str) -> Optional[dict]:
        """
        Fetch the pinned category registry memo and parse categories from it.

        The category memo is a normal memo whose content is a markdown list of
        categories. Format expected:

        ```
        # Categories
        - inbox: Default landing box
        - health: Medical, fitness, body
        - work: Career, job search, professional
        - finance: Money, debt, budget
        - project/dissertation: Luddite Loop work
        - personal: Relationships, home, life admin
        ```

        Returns:
            Dict with keys: uid, categories (list of {slug, description})
        """
        memo = await self.get_memo(category_memo_uid)
        if not memo:
            return None

        categories = self._parse_categories(memo["content"])
        return {"uid": memo["uid"], "categories": categories}

    # ---- Normalization (Memos API shape -> our stable shape) ----

    def _normalize_memo(self, raw: dict) -> dict:
        """
        Convert Memos API response to our stable internal format.

        Why: Memos renames fields between versions. This is the ONLY place
        that knows about Memos' field names. Everything downstream uses our
        stable keys.

        IMPORTANT: When upgrading Memos, check these field mappings first:
        - "name" field format changed in v0.22
        - "property.tags" replaced "tags" in v0.23
        - "rowStatus" was renamed in v0.24
        """
        # Extract UID from resource name (e.g. "memos/abc123" -> "abc123")
        name = raw.get("name", "")
        uid = raw.get("uid", name.split("/")[-1] if "/" in name else name)

        # Tags: in v0.24+ they live in property.tags
        tags = []
        prop = raw.get("property", {})
        if prop and isinstance(prop, dict):
            tags = prop.get("tags", [])

        return {
            "uid": uid,
            "name": name,
            "content": raw.get("content", ""),
            "tags": tags,
            "pinned": raw.get("pinned", False),
            "visibility": raw.get("visibility", "PRIVATE"),
            "created": raw.get("createTime", ""),
            "updated": raw.get("updateTime", ""),
            "has_task_list": prop.get("hasTaskList", False),
            "has_incomplete_tasks": prop.get("hasIncompleteTasks", False),
        }

    def _parse_categories(self, content: str) -> list[dict]:
        """
        Parse category definitions from the category memo content.

        Expected format: markdown list where each line is `- slug: description`

        Returns:
            List of {"slug": "...", "description": "..."}
        """
        categories = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("- ") and ":" in line:
                # Strip the "- " prefix
                entry = line[2:].strip()
                slug, _, description = entry.partition(":")
                slug = slug.strip().lower()
                description = description.strip()
                if slug:
                    categories.append({
                        "slug": slug,
                        "description": description,
                    })
        return categories

    # ---- Lifecycle ----

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()