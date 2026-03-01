# Memos Server Container

Self-hosted [Memos](https://github.com/usememos/memos) with the category dropdown JS injection baked into the image.

---

## What this container does

- Runs the official Memos server (version pinned in `config/versions.yaml`)
- Includes the `memos-category-dropdown.js` script for category routing UI
- Stores all memo data in a persistent volume

## Deployment options

### Option 1: Docker Compose (recommended)

From the repo root:

```bash
docker compose up -d memos
```

### Option 2: Railway

1. Create a new service on [Railway](https://railway.app)
2. Point it to this repo, set the Dockerfile path to `memos/Dockerfile`
3. Set environment variables:
   - `MEMOS_VERSION` (from `config/versions.yaml`)
4. Expose port `5230`

### Option 3: Supabase / any Docker host

```bash
docker build -f memos/Dockerfile -t memos-server .
docker run -d \
  --name memos-server \
  -p 5230:5230 \
  -v memos-data:/var/opt/memos \
  memos-server
```

### Option 4: Raw server with Docker

```bash
ssh root@YOUR_SERVER
curl -fsSL https://get.docker.com | sh
git clone YOUR_REPO_URL && cd memos-router
docker compose up -d memos
```

## JS Injection

The `memos-category-dropdown.js` script is baked into the image at `/usr/local/share/memos/category-dropdown.js`.

To install it:
1. Open Memos web UI
2. Go to Admin > Settings > Custom Script
3. Paste the contents of `scripts/memos-category-dropdown.js`

The script fetches its configuration from the API container's `/web-config` endpoint, so no hardcoded values need editing.

## Version pinning

Memos breaks its API between minor versions. Always pin the version:

```yaml
# config/versions.yaml
images:
  memos: "0.26.1"
```

Then update `MEMOS_VERSION` in `.env` to match. Before upgrading:
1. Read the [Memos changelog](https://github.com/usememos/memos/releases)
2. Update `MEMOS_VERSION` in `.env`
3. Check `src/memos_adapter.py` field mappings
4. Rebuild: `docker compose up -d --build memos`

## Volumes

| Volume | Mount point | Purpose |
|--------|-------------|---------|
| `memos-data` | `/var/opt/memos` | All memo data, user accounts, settings |

## Ports

| Port | Purpose |
|------|---------|
| `5230` | Memos web UI and API |

## Health check

```bash
curl http://localhost:5230/healthz
```

## Backup

```bash
docker cp memos-server:/var/opt/memos ./backup-memos-$(date +%Y%m%d)
```
