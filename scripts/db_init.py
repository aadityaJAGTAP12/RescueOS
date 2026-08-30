#!/usr/bin/env python3
"""
ReliefOS Phase 5A — Database Initialization Script

Creates the PostgreSQL + PostGIS schema and imports existing data.

Usage:
    # 1. Start PostgreSQL (via Docker)
    docker compose up -d

    # 2. Set DATABASE_URL
    export DATABASE_URL=postgresql://reliefos:reliefos@localhost:5432/reliefos

    # 3. Initialize database
    python scripts/db_init.py

    # Or run as module:
    python -m scripts.db_init
"""

import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("ERROR: DATABASE_URL not set.")
        print("")
        print("Usage:")
        print("  export DATABASE_URL=postgresql://reliefos:reliefos@localhost:5432/reliefos")
        print("  python scripts/db_init.py")
        print("")
        print("Quick start with Docker:")
        print("  docker compose up -d")
        print("  export DATABASE_URL=postgresql://reliefos:reliefos@localhost:5432/reliefos")
        print("  python scripts/db_init.py")
        sys.exit(1)

    print("=" * 60)
    print("ReliefOS Phase 5A — Database Initialization")
    print("=" * 60)

    # Step 1: Create tables
    print("\n[1/3] Creating database schema...")
    from agent.data.schema import get_engine, create_all_tables
    engine = get_engine(database_url)
    create_all_tables(engine)
    print("  Tables created successfully.")

    # Step 2: Initialize repository
    print("\n[2/3] Initializing repository...")
    from agent.data.repository import set_repository
    from agent.data.postgres_repository import PostgresRepository
    repo = PostgresRepository(engine=engine)
    set_repository(repo)
    print("  PostgresRepository initialized.")

    # Step 3: Run migration
    print("\n[3/3] Running data migration...")
    from agent.data.migration import run_full_migration
    summary = run_full_migration(repo)

    print("\n" + "=" * 60)
    print("Database initialization complete!")
    print("=" * 60)
    print(f"\nSummary:")
    print(f"  Districts: {len(summary.get('districts', []))}")
    print(f"  Settlements: {len(summary.get('settlements', []))}")
    if summary.get('flood_snapshot'):
        print(f"  Flood snapshot: {summary['flood_snapshot'].get('id', 'N/A')} "
              f"({summary['flood_snapshot'].get('polygon_count', 0)} polygons)")
    print(f"  Community reports imported: {summary.get('community_reports_imported', 0)}")
    print(f"  Overrides imported: {summary.get('overrides_imported', 0)}")
    print(f"\nDatabase: {database_url.split('@')[-1] if '@' in database_url else database_url}")


if __name__ == "__main__":
    main()
