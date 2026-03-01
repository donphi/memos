# Database Container

PostgreSQL database for the Memos Router service. Stores categories, memo events (immutable log), and routing state.

---

## What this container does

- Runs PostgreSQL 16 (Alpine-based, lightweight)
- Initializes the database on first run
- Tables are created automatically by the API container on startup

## When to use this container

| Scenario | Use this container? |
|----------|-------------------|
| Single-user, self-hosted, simple setup | No — use SQLite (default, no DB container needed) |
| Multi-user or want proper backups | Yes |
| Want to separate data from compute | Yes |
| Using managed Postgres (Supabase/Railway) | No — point `DATABASE_URL` at the managed instance |

## Deployment options

### Option 1: Docker Compose (recommended)

From the repo root:

```bash
docker compose up -d db
```

### Option 2: Railway

1. Create a Postgres instance on [Railway](https://railway.app)
2. Copy the `DATABASE_URL` from the service's Variables tab
3. Set it in your `.env` file — no need for this container

### Option 3: Supabase

1. Create a project at [supabase.com](https://supabase.com)
2. Go to Project Settings > Database > Connection string > URI
3. Set `DATABASE_URL` in `.env` to the URI

### Option 4: Raw server with Docker

```bash
docker build -t memos-router-db database/
docker run -d \
  --name memos-router-db \
  -p 5432:5432 \
  -e POSTGRES_DB=memos_router \
  -e POSTGRES_USER=router \
  -e POSTGRES_PASSWORD=your_secure_password \
  -v postgres-data:/var/lib/postgresql/data \
  memos-router-db
```

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `POSTGRES_DB` | `memos_router` | Database name |
| `POSTGRES_USER` | `router` | Database user |
| `POSTGRES_PASSWORD` | (required) | Database password — set in `.env` |

## Connection string format

```
postgresql://router:PASSWORD@db:5432/memos_router
```

- `db` is the Docker Compose service name (use `localhost` if running standalone)
- For Railway/Supabase, use their provided connection string

## Volumes

| Volume | Mount point | Purpose |
|--------|-------------|---------|
| `postgres-data` | `/var/lib/postgresql/data` | All database files |

## Ports

| Port | Purpose |
|------|---------|
| `5432` | PostgreSQL connections |

## Backup

```bash
# Dump the database
docker compose exec db pg_dump -U router memos_router > backup-$(date +%Y%m%d).sql

# Restore
docker compose exec -T db psql -U router memos_router < backup.sql
```

## Schema

Tables are managed by SQLAlchemy in `src/models.py`:

| Table | Purpose |
|-------|---------|
| `categories` | Active routing categories (synced from pinned memo) |
| `memo_events` | Immutable append-only log of all memo changes |
| `memo_routings` | Current box assignment per memo (fast lookups) |
