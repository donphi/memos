# Memos Router

Category-based routing, immutable event log, LLM action generation, and git-tracked undo for [Memos](https://github.com/usememos/memos).

---

## What this does

You write memos in Memos (web or mobile). Each memo gets routed to a category box — either by hashtag (`#box/health`) or by LLM classification. Every change is logged as an immutable event with full content snapshots and diffs. Optionally, an LLM reads each box and generates action files, with every LLM output tracked in git so you can diff or revert any change.

The category list is a single pinned memo. Edit it from web or mobile, and the router syncs automatically via webhook.

---

## Architecture — 3 containers

```
┌─────────────────┐     ┌──────────────────────────┐
│   Moe Memos     │     │  Memos Web UI            │
│   (iPhone)      │     │  + JS category dropdown  │
└────────┬────────┘     └────────┬─────────────────┘
         │ API                   │ API
         ▼                       ▼
┌──────────────────────────────────────────────────┐
│     CONTAINER 1: Memos Server (memos/)           │
│                                                  │
│  📌 Pinned category memo = source of truth       │
│  Webhook fires on every create / update / delete │
│  JS dropdown injection baked into image          │
└────────────────────┬─────────────────────────────┘
                     │ HTTP POST /webhook
                     ▼
┌──────────────────────────────────────────────────┐
│     CONTAINER 3: API Router (api/)               │
│                                                  │
│  1. Category memo changed? → re-sync DB          │
│  2. Route memo: hashtag → content scan → LLM     │
│  3. Log immutable event (snapshot + unified diff) │
│  4. (Optional) Generate actions → git commit      │
│  5. Serve /web-config for JS dropdown            │
└────────────────────┬─────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
┌──────────┐  ┌───────────┐  ┌──────────────┐
│CONTAINER │  │ LLM API   │  │ Git repo     │
│2: DB     │  │ OpenRouter │  │ data/actions │
│(database)│  │ Anthropic  │  │ (versioned)  │
│PostgreSQL│  │ Ollama     │  └──────────────┘
└──────────┘  └───────────┘

┌──────────────────────────────────────────────────┐
│     LOCAL SYNC (local/)                          │
│                                                  │
│  All 3 containers locally + sync.py to pull      │
│  data from remote for offline access / backup    │
└──────────────────────────────────────────────────┘
```

### Container summary

| # | Container | Directory | Purpose | Can run on |
|---|-----------|-----------|---------|------------|
| 1 | **Memos** | `memos/` | Memos server + JS injection | Railway, Supabase, any Docker host |
| 2 | **Database** | `database/` | PostgreSQL for router data | Railway, Supabase, any Docker host, or skip (use SQLite / managed Postgres) |
| 3 | **API** | `api/` | FastAPI router, webhook, LLM, events | Railway, Supabase, any Docker host |
| 4 | **Local** | `local/` | Full local mirror + sync script | Your machine |

---

## Repository structure

```
memos-router/
├── docker-compose.yml          # 3-container orchestration
├── .env.example                # Environment variable template
├── .dockerignore               # Docker build exclusions
├── .gitignore
├── requirements.txt            # Python dependencies (shared by API)
│
├── config/                     # ALL configuration lives here
│   ├── paths.yaml              # Every path, URL, directory, location
│   ├── tuning.yaml             # Every hyperparameter, threshold, model setting
│   ├── versions.yaml           # Every version pin (images, Python packages)
│   └── prompts/                # LLM prompt templates (hot-reloadable)
│       ├── classify.txt        # Memo classification prompt
│       └── action_generate.txt # Action item generation prompt
│
├── src/                        # Python source (used by API container)
│   ├── server.py               # FastAPI entrypoint, all routes
│   ├── config_loader.py        # Loads paths.yaml + tuning.yaml
│   ├── models.py               # SQLAlchemy schema
│   ├── memos_adapter.py        # Memos REST API adapter
│   ├── category_sync.py        # Syncs category memo with DB
│   ├── event_logger.py         # Immutable event log
│   ├── router.py               # Memo routing logic
│   ├── llm_provider.py         # Provider-agnostic LLM client
│   └── action_generator.py     # LLM action generation + git tracking
│
├── scripts/                    # Setup, build, and UI injection scripts
│   ├── seed_categories.py      # First-run: creates pinned category memo
│   ├── memos-category-dropdown.js  # Memos UI category picker injection
│   └── generate_requirements.py    # Generates requirements.txt from versions.yaml
│
├── memos/                      # Container 1: Memos server
│   ├── Dockerfile
│   └── README.md
│
├── database/                   # Container 2: PostgreSQL
│   ├── Dockerfile
│   ├── init.sql
│   └── README.md
│
├── api/                        # Container 3: FastAPI router
│   ├── Dockerfile
│   └── README.md
│
└── local/                      # Container 4: Local sync
    ├── docker-compose.local.yml
    ├── sync.py
    └── README.md
```

---

## Configuration — zero hardcoded values

Every tuneable value lives in `config/`. Nothing is hardcoded in any Python file, JavaScript file, or Dockerfile.

### `config/versions.yaml` — version pins

Every version number for images and dependencies:

| Section | Keys |
|---------|------|
| `images.memos` | Memos server image tag (e.g. `0.24.1`) |
| `images.python` | Python base image tag (e.g. `3.12-slim`) |
| `images.postgres` | PostgreSQL base image tag (e.g. `16-alpine`) |
| `python_packages.*` | Every pinned Python dependency version |

After editing `versions.yaml`, run:

```bash
python scripts/generate_requirements.py   # regenerates requirements.txt
```

Then update `.env` to match the image versions and rebuild:

```bash
docker compose up -d --build
```

### `config/paths.yaml` — locations

Every path, URL, directory, and endpoint reference:

| Section | Keys |
|---------|------|
| `memos` | `base_url`, `api_version`, `webhook_url` |
| `database` | `url` |
| `llm` | `base_url` |
| `server` | `host`, `port` |
| `data` | `actions_dir`, `data_dir` |
| `prompts` | `dir` |
| `git` | `user_email`, `user_name` |
| `containers` | `memos_internal_url`, `router_internal_url`, `db_internal_url` |

### `config/tuning.yaml` — hyperparameters

Every threshold, timeout, model setting, and tuneable value:

| Section | Keys |
|---------|------|
| `memos` | `request_timeout_seconds`, `api_token` |
| `categories` | `memo_uid`, `tag_prefix`, `default_category`, `sync_on_startup` |
| `routing` | `enable_content_scan`, `enable_llm_fallback`, `ignore_tags` |
| `llm` | `provider`, `api_key`, `request_timeout_seconds`, `max_retries`, `anthropic_api_version`, `extra_headers` |
| `llm.models.classify` | `id`, `max_tokens`, `temperature` |
| `llm.models.action_generate` | `id`, `max_tokens`, `temperature` |
| `llm.models.summarise` | `id`, `max_tokens`, `temperature` |
| `database` | `echo` |
| `events` | `preview_length`, `diff_format`, `recent_memos_limit`, `action_history_limit` |
| `server` | `log_level`, `cors_origins` |
| `web_ui` | `dropdown_refresh_interval_ms`, `dropdown_poll_interval_ms`, `mutation_observer_debounce_ms` |
| `debug` | `llm_response_preview_length`, `llm_error_preview_length` |

### `config/prompts/` — LLM prompt templates

| File | Injectable variables | Purpose |
|------|---------------------|---------|
| `classify.txt` | `{{categories}}`, `{{content}}`, `{{default_category}}` | Route untagged memo to a category |
| `action_generate.txt` | `{{category_slug}}`, `{{category_description}}`, `{{recent_memos}}`, `{{existing_actions}}` | Generate action items from box contents |

Prompts reload on every call — edit without restarting.

### Environment variable overrides

Secrets and deployment-specific values override YAML via env vars:

| Env var | Overrides | File |
|---------|-----------|------|
| `MEMOS_BASE_URL` | `paths.memos.base_url` | paths.yaml |
| `MEMOS_API_TOKEN` | `tuning.memos.api_token` | tuning.yaml |
| `CATEGORY_MEMO_UID` | `tuning.categories.memo_uid` | tuning.yaml |
| `DATABASE_URL` | `paths.database.url` | paths.yaml |
| `LLM_API_KEY` | `tuning.llm.api_key` | tuning.yaml |
| `LLM_BASE_URL` | `paths.llm.base_url` | paths.yaml |
| `ROUTER_PORT` | `paths.server.port` | paths.yaml |
| `ROUTER_HOST` | `paths.server.host` | paths.yaml |
| `LLM_CLASSIFY_ENABLED` | `tuning.routing.enable_llm_fallback` | tuning.yaml |

---

## Quick start

```bash
# 1. Configure
cp .env.example .env
# Edit: MEMOS_API_TOKEN, POSTGRES_PASSWORD

# 2. Start all 3 containers
docker compose up -d

# 3. Create category memo
docker compose exec api python scripts/seed_categories.py
# Copy printed UID → .env as CATEGORY_MEMO_UID

# 4. Pin the category memo in Memos UI

# 5. Configure webhook in Memos:
#    Settings > Webhooks > Add
#    URL: http://api:8780/webhook

# 6. Install the category dropdown:
#    Memos Admin > Settings > Custom Script
#    Paste contents of scripts/memos-category-dropdown.js

# 7. Restart with UID configured
docker compose restart api

# 8. (Optional) Enable LLM classification
#    Set LLM_API_KEY in .env
#    Set enable_llm_fallback: true in config/tuning.yaml
#    docker compose restart api
```

---

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/webhook` | Receives Memos webhooks. Routes memo, logs event, syncs categories. |
| GET | `/categories` | Active categories (used by JS dropdown). |
| GET | `/history/{memo_uid}` | Full event history for a memo. |
| GET | `/box/{category_slug}` | Recent memos in a box. |
| POST | `/actions/{slug}/generate` | Run LLM action generation for a box. |
| GET | `/actions/{slug}` | Current action file content. |
| GET | `/actions/{slug}/history` | Git log of action file changes. |
| POST | `/actions/{slug}/revert` | Git revert last LLM change. |
| GET | `/actions/{slug}/diff/{hash}` | Diff for a specific commit. |
| GET | `/health` | Health check. |
| GET | `/web-config` | Config values for JS injection. |

---

## Database options

### Option 1: Included PostgreSQL container (default)

The `db` service in `docker-compose.yml` runs Postgres 16. Set `POSTGRES_PASSWORD` in `.env`.

### Option 2: SQLite (simplest, single-user)

Skip the `db` service. Set in `.env`:

```bash
DATABASE_URL=sqlite:///data/router.db
```

Start without the DB container:

```bash
docker compose up -d memos api
```

### Option 3: Supabase (managed Postgres)

1. Create a project at [supabase.com](https://supabase.com)
2. Copy the connection URI from Project Settings > Database
3. Set `DATABASE_URL` in `.env`
4. Start without the DB container: `docker compose up -d memos api`

### Option 4: Railway (managed Postgres)

1. Create a Postgres instance on [Railway](https://railway.app)
2. Copy `DATABASE_URL` from the Variables tab
3. Set in `.env`, start without DB container

---

## LLM provider setup

All LLM config lives in `config/tuning.yaml`. The API key is the only value that MUST be an env var.

### OpenRouter (recommended)

```yaml
# tuning.yaml
llm:
  provider: "openrouter"
  models:
    classify:
      id: "anthropic/claude-sonnet-4-20250514"
      max_tokens: 30
      temperature: 0.0
```

```bash
# .env
LLM_API_KEY=sk-or-v1-xxxx
```

### Anthropic (direct)

```yaml
llm:
  provider: "anthropic"
```

```bash
# paths.yaml
llm:
  base_url: "https://api.anthropic.com"
```

### Ollama (local, free)

```yaml
llm:
  provider: "ollama"
  models:
    classify:
      id: "llama3.2"
```

```bash
# paths.yaml
llm:
  base_url: "http://ollama:11434"
```

---

## Deploying to a server

### Fresh VPS setup (Hetzner, DigitalOcean, etc.)

```bash
ssh root@YOUR_IP
curl -fsSL https://get.docker.com | sh
git clone YOUR_REPO_URL && cd memos-router
cp .env.example .env
# Edit .env with your values
docker compose up -d
```

### Reverse proxy (Caddy — automatic HTTPS)

```bash
apt install caddy
```

```
# /etc/caddy/Caddyfile
memos.yourdomain.com {
    reverse_proxy localhost:5230
}

router.yourdomain.com {
    reverse_proxy localhost:8780
}
```

```bash
systemctl restart caddy
```

### Firewall

```bash
ufw allow 22       # SSH
ufw allow 80       # Caddy HTTP
ufw allow 443      # Caddy HTTPS
ufw enable
```

Don't expose 5230, 5432, or 8780 directly — Caddy handles external access.

---

## Local sync (offline access / backup)

Run the full stack locally and sync from your remote server:

```bash
cd local/
cp ../.env.example .env
# Add REMOTE_MEMOS_URL, REMOTE_MEMOS_TOKEN, LOCAL_MEMOS_TOKEN
docker compose -f docker-compose.local.yml up -d
python sync.py
```

See `local/README.md` for full details.

---

## Memos version pinning

Memos breaks its API between minor versions. The adapter pattern isolates this:

```bash
# 1. Read the Memos changelog
# 2. Update images.memos in config/versions.yaml
# 3. Update MEMOS_VERSION in .env to match
# 4. Check src/memos_adapter.py field mappings
# 5. docker compose up -d --build && docker compose logs api
```

Only `src/memos_adapter.py` knows Memos API internals. Every other file uses stable internal dicts.

---

## Mobile experience (Moe Memos)

The pinned category memo is visible at the top of your feed. Type `#box/health` manually when writing a memo. The webhook fires, same routing logic applies.

No category dropdown on mobile (native app can't execute custom JS). If LLM is enabled, it classifies automatically. Otherwise it lands as "unrouted".

---

## How git-tracked actions work

When you call `POST /actions/health/generate`:

1. Router reads recent memos in the health box
2. Reads the current `data/actions/health.md` file
3. Sends both to the LLM with the `action_generate.txt` prompt
4. Writes the LLM output to `health.md`
5. Runs `git add health.md && git commit` with metadata
6. Returns the diff

To undo: `POST /actions/health/revert` — runs `git revert`.

To see history: `GET /actions/health/history` — returns git log.

---

## Backups

```bash
# Memos data
docker cp memos-server:/var/opt/memos ./backup-memos-$(date +%Y%m%d)

# Database (Postgres)
docker compose exec db pg_dump -U router memos_router > backup-db-$(date +%Y%m%d).sql

# Database (SQLite, if used)
docker cp memos-router-api:/app/data/router.db ./backup-router-$(date +%Y%m%d).db

# Action file git history
docker cp memos-router-api:/app/data/actions ./backup-actions-$(date +%Y%m%d)
```

---

## Moving servers

Everything is in this repo:

1. `docker-compose.yml` + `.env` — infrastructure
2. `config/paths.yaml` — all paths and URLs
3. `config/tuning.yaml` — all hyperparameters
4. `config/prompts/*.txt` — LLM prompts
5. `scripts/seed_categories.py` — first-run category creation
6. `scripts/memos-category-dropdown.js` — web UI injection
7. `src/memos_adapter.py` — the only file that touches Memos API specifics

Data to migrate:
- Memos volume (`memos-data`) — your actual memos
- Router database (Postgres or SQLite)
- Actions git repo (`data/actions/`) — LLM output history

---

## Per-container documentation

Each container has its own README with deployment options and configuration:

- [`memos/README.md`](memos/README.md) — Memos server container
- [`database/README.md`](database/README.md) — PostgreSQL database container
- [`api/README.md`](api/README.md) — FastAPI router container
- [`local/README.md`](local/README.md) — Local sync setup
