# ============================================================================
# MEMOS SERVER CONTAINER
# PURPOSE: Self-hosted Memos with category dropdown JS injection baked in
# BASE: Official neosmemo/memos image
# ============================================================================
#
# BUILD CONTEXT: Built from repo root via docker compose.
# VERSION: Passed as build arg from docker-compose.yml, sourced from
#          config/versions.yaml → .env → MEMOS_VERSION.
#          No default — must be set explicitly.
# ============================================================================
ARG MEMOS_VERSION
FROM neosmemo/memos:${MEMOS_VERSION}

LABEL maintainer="don"
LABEL description="Memos server with category dropdown injection"

COPY scripts/memos-category-dropdown.js /usr/local/share/memos/category-dropdown.js
