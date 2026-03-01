#!/usr/bin/env python3
# ============================================================================
# LOCAL SYNC SCRIPT
# PURPOSE: Pull data from remote Memos + Router into local containers
# ============================================================================
"""
Syncs data from your remote deployment to local containers.

Usage:
    # Set these in your .env or export them:
    export REMOTE_MEMOS_URL=https://memos.yourdomain.com
    export REMOTE_ROUTER_URL=https://router.yourdomain.com
    export REMOTE_MEMOS_TOKEN=your_remote_token
    export LOCAL_MEMOS_URL=http://localhost:5230
    export LOCAL_ROUTER_URL=http://localhost:8780
    export LOCAL_MEMOS_TOKEN=your_local_token

    python sync.py
"""

import os
import sys
import json
import httpx
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def sync_categories(remote_router_url: str, local_router_url: str):
    """Fetch categories from remote and verify they exist locally."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{remote_router_url}/categories")
        resp.raise_for_status()
        remote_cats = resp.json().get("categories", [])

        resp = await client.get(f"{local_router_url}/categories")
        local_cats = resp.json().get("categories", [])

        remote_slugs = {c["slug"] for c in remote_cats}
        local_slugs = {c["slug"] for c in local_cats}

        missing = remote_slugs - local_slugs
        if missing:
            print(f"  Categories missing locally: {missing}")
            print("  These will sync when the category memo webhook fires.")
        else:
            print(f"  All {len(remote_cats)} categories present locally.")


async def sync_memos(remote_memos_url: str, remote_token: str,
                     local_memos_url: str, local_token: str,
                     api_version: str = "v1"):
    """Fetch all memos from remote and create missing ones locally."""
    remote_headers = {"Authorization": f"Bearer {remote_token}"}
    local_headers = {"Authorization": f"Bearer {local_token}"}

    async with httpx.AsyncClient(timeout=60) as client:
        print("  Fetching remote memos...")
        all_remote = []
        page_token = None
        while True:
            params = {}
            if page_token:
                params["pageToken"] = page_token
            resp = await client.get(
                f"{remote_memos_url}/api/{api_version}/memos",
                headers=remote_headers, params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            all_remote.extend(data.get("memos", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        print(f"  Found {len(all_remote)} remote memos.")

        print("  Fetching local memos...")
        all_local = []
        page_token = None
        while True:
            params = {}
            if page_token:
                params["pageToken"] = page_token
            resp = await client.get(
                f"{local_memos_url}/api/{api_version}/memos",
                headers=local_headers, params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            all_local.extend(data.get("memos", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        local_uids = {m.get("uid", "") for m in all_local}
        to_sync = [m for m in all_remote if m.get("uid", "") not in local_uids]

        print(f"  {len(to_sync)} memos to sync.")

        for memo in to_sync:
            content = memo.get("content", "")
            visibility = memo.get("visibility", "PRIVATE")
            try:
                resp = await client.post(
                    f"{local_memos_url}/api/{api_version}/memos",
                    headers=local_headers,
                    json={"content": content, "visibility": visibility},
                )
                resp.raise_for_status()
                print(f"    Synced: {memo.get('uid', 'unknown')[:12]}...")
            except Exception as e:
                print(f"    Failed to sync {memo.get('uid', 'unknown')[:12]}: {e}")

        print(f"  Sync complete. {len(to_sync)} memos synced.")


async def main():
    remote_memos = os.environ.get("REMOTE_MEMOS_URL", "")
    remote_router = os.environ.get("REMOTE_ROUTER_URL", "")
    remote_token = os.environ.get("REMOTE_MEMOS_TOKEN", "")
    local_memos = os.environ.get("LOCAL_MEMOS_URL", "http://localhost:5230")
    local_router = os.environ.get("LOCAL_ROUTER_URL", "http://localhost:8780")
    local_token = os.environ.get("LOCAL_MEMOS_TOKEN", "")

    if not remote_memos or not remote_token:
        print("Error: Set REMOTE_MEMOS_URL and REMOTE_MEMOS_TOKEN")
        sys.exit(1)
    if not local_token:
        print("Error: Set LOCAL_MEMOS_TOKEN (create in local Memos > Settings > Access Tokens)")
        sys.exit(1)

    print("=== Memos Local Sync ===")
    print(f"Remote Memos:  {remote_memos}")
    print(f"Remote Router: {remote_router}")
    print(f"Local Memos:   {local_memos}")
    print(f"Local Router:  {local_router}")
    print()

    if remote_router:
        print("[1/2] Syncing categories...")
        await sync_categories(remote_router, local_router)
    else:
        print("[1/2] Skipping category sync (no REMOTE_ROUTER_URL)")

    print("[2/2] Syncing memos...")
    await sync_memos(remote_memos, remote_token, local_memos, local_token)

    print()
    print("Done. Your local instance is now a mirror of the remote.")


if __name__ == "__main__":
    asyncio.run(main())
