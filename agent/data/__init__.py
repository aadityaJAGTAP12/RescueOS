"""
Phase 3+5A: Generalized Data Layer

This package provides:
- models.py: Data schemas (District, Settlement, FloodSnapshot, etc.)
- repository.py: Abstract repository interface + InMemoryRepository
- postgres_repository.py: PostgreSQL + PostGIS implementation
- schema.py: SQLAlchemy database schema definitions
- migration.py: Import existing data into the generalized layer

Usage:
    from agent.data import get_repository, run_full_migration

    repo = get_repository()  # auto-selects based on DATABASE_URL
    run_full_migration(repo)

    # Now query generalized data
    snapshot = repo.get_latest_flood_snapshot("sivasagar")
    settlement = repo.resolve_location("sivasagar_flood_zone")

Environment variables:
    DATABASE_URL: PostgreSQL connection string (enables PostgresRepository)
    RELIEFOS_MEMORY: Set to "1" to force InMemoryRepository
"""

from agent.data.repository import get_repository, set_repository, reset_repository, InMemoryRepository
from agent.data.migration import run_full_migration

__all__ = [
    "get_repository",
    "set_repository",
    "reset_repository",
    "InMemoryRepository",
    "run_full_migration",
]
