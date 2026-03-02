# API Container (Memos Router)

FastAPI service that receives Memos webhooks, routes memos to category boxes, logs immutable events, and optionally generates LLM-powered action items.

---

## What this container does

1. **Webhook receiver** — listens for Memos create/update/delete events
2. **Category routing** — routes memos by hashtag (`#box/health`) or LLM classification
3. **Immutable event log** — every memo change is recorded with full snapshots and diffs
4. **Action generation** — LLM reads box contents and generates action items, git-tracked
5. **Category sync** — reads the pinned category memo and keeps the DB in sync
6. **Web config API** — serves configuration to the JS dropdown injection

## Deployment options

### Option 1: Docker Compose (recommended)

From the repo root:

```bash
docker compose up -d api
```

### Option 2: Railway

1. Create a new service on [Railway](https://railway.app)
2. Set the Dockerfile path to `api/Dockerfile`
3. Set environment variables (see below)
4. Expose port `8780`

### Option 3: Supabase / any Docker host

```bash
docker build -f api/Dockerfile -t memos-router-api .
docker run -d \
  --name memos-router-api \
  -p 8780:8780 \
  -e MEMOS_BASE_URL=http://your-memos:5230 \
  -e MEMOS_API_TOKEN=your_token \
  -e DATABASE_URL=postgresql://router:pass@your-db:5432/memos_router \
  -e LLM_API_KEY=sk-or-v1-xxx \
  -v router-data:/app/data \
  -v ./config:/app/config:ro \
  memos-router-api
```

### Option 4: Raw server with Docker

```bash
ssh root@YOUR_SERVER
docker compose up -d api
```

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `MEMOS_BASE_URL` | Yes | URL of the Memos server |
| `MEMOS_API_TOKEN` | Yes | Bearer token from Memos Settings > Access Tokens |
| `CATEGORY_MEMO_UID` | Yes | UID of the pinned category memo |
| `DATABASE_URL` | No | Override database connection (default: SQLite) |
| `LLM_API_KEY` | No | API key for LLM provider (enables classification) |
| `LLM_BASE_URL` | No | Override LLM endpoint URL |
| `LLM_CLASSIFY_ENABLED` | No | `true`/`false` to toggle LLM classification |
| `ROUTER_PORT` | No | Override server port (default: 8780) |
| `ROUTER_HOST` | No | Override server bind address (default: 0.0.0.0) |

## Configuration

All tuneable values live in two YAML files mounted at `/app/config/`:

| File | Contents |
|------|----------|
| `config/paths.yaml` | Every path, URL, directory, and location |
| `config/tuning.yaml` | Every hyperparameter, threshold, timeout, model setting |
| `config/prompts/*.txt` | LLM prompt templates (hot-reloadable) |

See the root README for full config documentation.

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/webhook` | Receives Memos webhooks |
| GET | `/categories` | Active categories (used by JS dropdown) |
| GET | `/history/{memo_uid}` | Full event history for a memo |
| GET | `/box/{category_slug}` | Recent memos in a box |
| POST | `/actions/{slug}/generate` | Run LLM action generation |
| GET | `/actions/{slug}` | Current action file content |
| GET | `/actions/{slug}/history` | Git log of action file changes |
| POST | `/actions/{slug}/revert` | Git revert last LLM change |
| GET | `/actions/{slug}/diff/{hash}` | Diff for a specific commit |
| GET | `/health` | Health check |
| GET | `/web-config` | Config values for JS injection |

## Volumes

| Volume | Mount point | Purpose |
|--------|-------------|---------|
| `router-data` | `/app/data` | SQLite DB (if used) and git-tracked action files |
| `./config` | `/app/config` (read-only) | Configuration YAML files and prompts |

## Ports

| Port | Purpose |
|------|---------|
| `8780` | API server |

## First-run setup

```bash
# Create the category memo in Memos
docker compose exec api python scripts/seed_categories.py

# Copy the printed UID into .env as CATEGORY_MEMO_UID
# Then recreate (restart does NOT re-read .env):
docker compose up -d api
```

## Source files

| File | Purpose |
|------|---------|
| `src/server.py` | FastAPI entrypoint, all routes |
| `src/config_loader.py` | Loads paths.yaml + tuning.yaml, env overrides |
| `src/models.py` | SQLAlchemy schema (categories, events, routings) |
| `src/memos_adapter.py` | Memos REST API adapter (version-specific) |
| `src/category_sync.py` | Syncs pinned category memo with DB |
| `src/event_logger.py` | Immutable event log with snapshots and diffs |
| `src/router.py` | Memo routing logic (hashtag + LLM) |
| `src/llm_provider.py` | Provider-agnostic LLM client |
| `src/action_generator.py` | LLM action generation with git tracking |
