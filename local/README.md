# Local Sync Container

Run the entire Memos Router stack locally and sync data from your remote deployment.

---

## What this does

Spins up all three services (Memos, Database, API) on your local machine and provides a sync script to pull all memos, categories, and routing data from your remote server. Use this for:

- **Offline access** — work with your memos when you have no internet
- **Backup** — keep a local copy of everything
- **Migration** — move between servers
- **Development** — test changes against real data

## Quick start

```bash
cd local/

# Create your local .env
cat > .env << 'EOF'
# Versions (from config/versions.yaml)
MEMOS_VERSION=0.26.1
PYTHON_VERSION=3.12-slim
POSTGRES_VERSION=16-alpine

MEMOS_API_TOKEN=your_local_token
CATEGORY_MEMO_UID=your_category_uid
LOCAL_POSTGRES_PASSWORD=localdev
LOCAL_MEMOS_PORT=5230
LOCAL_DB_PORT=5432
LOCAL_ROUTER_PORT=8780

# Remote server details (for sync)
REMOTE_MEMOS_URL=https://memos.yourdomain.com
REMOTE_ROUTER_URL=https://router.yourdomain.com
REMOTE_MEMOS_TOKEN=your_remote_api_token
LOCAL_MEMOS_URL=http://localhost:5230
LOCAL_ROUTER_URL=http://localhost:8780
LOCAL_MEMOS_TOKEN=your_local_api_token
EOF

# Start local stack
docker compose -f docker-compose.local.yml up -d

# Wait for services to be healthy, then create a local API token in Memos UI

# Sync data from remote
pip install httpx
python sync.py
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│                 LOCAL MACHINE                     │
│                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │  Memos   │  │ Postgres │  │  API Router  │  │
│  │  :5230   │  │  :5432   │  │    :8780     │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
│                                                   │
│  sync.py ←──── pulls from ────→ REMOTE SERVER   │
└─────────────────────────────────────────────────┘
```

## Sync script

The `sync.py` script:

1. Fetches categories from the remote router and checks they exist locally
2. Fetches all memos from the remote Memos server
3. Creates any missing memos in the local Memos instance
4. Reports what was synced

Run it as often as you want — it's idempotent (won't duplicate memos).

## Environment variables

| Variable | Purpose |
|----------|---------|
| `REMOTE_MEMOS_URL` | URL of your remote Memos server |
| `REMOTE_ROUTER_URL` | URL of your remote router API |
| `REMOTE_MEMOS_TOKEN` | API token for the remote Memos server |
| `LOCAL_MEMOS_URL` | URL of local Memos (default: `http://localhost:5230`) |
| `LOCAL_ROUTER_URL` | URL of local router (default: `http://localhost:8780`) |
| `LOCAL_MEMOS_TOKEN` | API token for the local Memos server |
| `LOCAL_POSTGRES_PASSWORD` | Password for local Postgres (default: `localdev`) |

## Ports

All ports are configurable via `.env`:

| Service | Default port | Env var |
|---------|-------------|---------|
| Memos | 5230 | `LOCAL_MEMOS_PORT` |
| Database | 5432 | `LOCAL_DB_PORT` |
| API | 8780 | `LOCAL_ROUTER_PORT` |

## Volumes

| Volume | Purpose |
|--------|---------|
| `memos-local-data` | Local Memos data |
| `postgres-local-data` | Local Postgres data |
| `router-local-data` | Local router data (SQLite fallback + action files) |
