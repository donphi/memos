-- ============================================================================
-- DATABASE INITIALIZATION
-- Runs once when the Postgres container is first created.
-- The router's SQLAlchemy models handle table creation via create_all().
-- This script just ensures the database and extensions exist.
-- ============================================================================

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- The database itself is created by POSTGRES_DB env var.
-- Tables are created by SQLAlchemy's Base.metadata.create_all() on router startup.
