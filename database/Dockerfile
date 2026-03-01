# ============================================================================
# DATABASE CONTAINER
# PURPOSE: PostgreSQL database for the Memos Router service
# ============================================================================
#
# VERSION: POSTGRES_VERSION passed as build arg from docker-compose.yml,
#          sourced from config/versions.yaml. No default — must be set.
# ============================================================================
ARG POSTGRES_VERSION
FROM postgres:${POSTGRES_VERSION}

LABEL maintainer="don"
LABEL description="PostgreSQL database for Memos Router"

COPY init.sql /docker-entrypoint-initdb.d/01-init.sql
