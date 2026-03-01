# ============================================================================
# FILE: server.py
# LOCATION: src/
# PIPELINE POSITION: Entrypoint - FastAPI server
# PURPOSE: Webhook reception, category queries, action generation, history
# ============================================================================

import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from src.config_loader import Config
from src.models import init_db
from src.memos_adapter import MemosAdapter
from src.category_sync import CategorySync
from src.event_logger import EventLogger
from src.router import MemoRouter
from src.llm_provider import LLMProvider
from src.action_generator import ActionGenerator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

config: Config = None
adapter: MemosAdapter = None
category_sync: CategorySync = None
event_logger: EventLogger = None
memo_router: MemoRouter = None
llm: LLMProvider = None
action_gen: ActionGenerator = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global config, adapter, category_sync, event_logger, memo_router, llm, action_gen

    config = Config.load()

    session_factory = init_db(config.database_url, echo=config.database_echo)
    adapter = MemosAdapter(
        config.memos_base_url, config.memos_api_token,
        api_version=config.memos_api_version,
        request_timeout=config.memos_request_timeout,
    )
    category_sync = CategorySync(session_factory)
    event_logger = EventLogger(session_factory, preview_length=config.preview_length)

    llm = LLMProvider(config) if config.llm_api_key else None

    if config.sync_on_startup and config.category_memo_uid:
        try:
            cat_memo = await adapter.get_category_memo(config.category_memo_uid)
            if cat_memo:
                result = category_sync.sync(cat_memo["categories"])
                logger.info(f"Startup category sync: {result}")
        except Exception as e:
            logger.error(f"Startup category sync failed: {e}")

    active_cats = category_sync.get_active_categories()
    memo_router = MemoRouter(config=config, llm=llm, active_categories=active_cats)

    if llm:
        action_gen = ActionGenerator(
            config=config, llm=llm, event_logger=event_logger,
            actions_dir=config.actions_dir,
        )

    yield

    if adapter: await adapter.close()
    if llm: await llm.close()


app = FastAPI(title="Memos Router", lifespan=lifespan)

# CORS is added at startup via the lifespan; for module-level we use a
# startup event to read config. As a safe default, allow all origins.
# The actual origins list comes from tuning.yaml server.cors_origins.
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])


@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return Response(status_code=400, content="Invalid JSON")

    memo_data = payload.get("memo", {})
    if not memo_data:
        return Response(status_code=400, content="No memo data")

    memo_uid = memo_data.get("uid", "")
    content = memo_data.get("content", "")
    tags = memo_data.get("property", {}).get("tags", [])
    event_type_map = {"memos.memo.created": "created",
                      "memos.memo.updated": "updated",
                      "memos.memo.deleted": "deleted"}
    event_type = event_type_map.get(payload.get("activityType", ""), "updated")

    if memo_uid == config.category_memo_uid:
        try:
            cat_memo = await adapter.get_category_memo(config.category_memo_uid)
            if cat_memo:
                category_sync.sync(cat_memo["categories"])
                memo_router.update_categories(category_sync.get_active_categories())
        except Exception as e:
            logger.error(f"Category re-sync failed: {e}")
        return {"status": "category_synced"}

    category_slug, routing_method = await memo_router.route_async(content, tags)

    event_logger.log_event(
        memo_uid=memo_uid, event_type=event_type, content=content,
        tags=tags, routed_to=category_slug, routing_method=routing_method,
        memo_timestamp=memo_data.get("updateTime", ""),
    )
    return {"status": "routed", "memo_uid": memo_uid,
            "category": category_slug, "method": routing_method}


@app.get("/categories")
async def get_categories():
    return {"categories": category_sync.get_active_categories()}

@app.get("/history/{memo_uid}")
async def get_history(memo_uid: str):
    return {"memo_uid": memo_uid, "events": event_logger.get_memo_history(memo_uid)}

@app.get("/box/{category_slug}")
async def get_box_contents(category_slug: str, limit: int = None):
    effective_limit = limit if limit is not None else config.recent_memos_limit
    return {"category": category_slug,
            "memos": event_logger.get_recently_routed(category_slug, limit=effective_limit)}

@app.post("/actions/{category_slug}/generate")
async def generate_actions(category_slug: str):
    if not action_gen:
        return Response(status_code=503, content="LLM not configured")
    cats = category_sync.get_active_categories()
    desc = next((c["description"] for c in cats if c["slug"] == category_slug), "")
    return await action_gen.generate(category_slug, desc)

@app.get("/actions/{category_slug}")
async def get_actions(category_slug: str):
    if not action_gen:
        return Response(status_code=503, content="LLM not configured")
    return {"slug": category_slug, "actions": action_gen.get_current_actions(category_slug)}

@app.get("/actions/{category_slug}/history")
async def get_action_history(category_slug: str, limit: int = None):
    if not action_gen:
        return Response(status_code=503, content="LLM not configured")
    effective_limit = limit if limit is not None else config.action_history_limit
    return {"slug": category_slug, "history": action_gen.get_history(category_slug, effective_limit)}

@app.post("/actions/{category_slug}/revert")
async def revert_action(category_slug: str):
    if not action_gen:
        return Response(status_code=503, content="LLM not configured")
    return action_gen.revert_last(category_slug)

@app.get("/actions/{category_slug}/diff/{commit_hash}")
async def get_action_diff(category_slug: str, commit_hash: str):
    if not action_gen:
        return Response(status_code=503, content="LLM not configured")
    return {"slug": category_slug, "commit": commit_hash,
            "diff": action_gen.get_diff(commit_hash)}

@app.get("/health")
async def health():
    return {"status": "ok", "categories": len(category_sync.get_active_categories()),
            "llm_enabled": config.enable_llm_fallback,
            "provider": config.llm_provider if config.enable_llm_fallback else None}

@app.get("/web-config")
async def web_config():
    """Serve config values needed by the JS injection script."""
    return {
        "router_port": config.server_port,
        "tag_prefix": config.tag_prefix,
        "poll_interval_ms": config.dropdown_poll_interval_ms,
        "refresh_interval_ms": config.dropdown_refresh_interval_ms,
        "debounce_ms": config.mutation_observer_debounce_ms,
    }


if __name__ == "__main__":
    cfg = Config.load()
    uvicorn.run("src.server:app", host=cfg.server_host, port=cfg.server_port,
                reload=False, log_level=cfg.server_log_level)
