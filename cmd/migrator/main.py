"""
Database Migrator Entry Point.

Applies database migrations using SQL files.
"""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv


# Load environment variables
load_dotenv()


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/product_service",
)

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"


async def get_applied_migrations(conn: asyncpg.Connection) -> set[str]:
    """
    Get list of already applied migrations.
    
    Args:
        conn: Database connection.
        
    Returns:
        Set of applied migration names.
    """
    # Create migrations tracking table if not exists
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL UNIQUE,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    rows = await conn.fetch("SELECT name FROM _migrations")
    return {row["name"] for row in rows}


async def apply_migration(
    conn: asyncpg.Connection,
    migration_path: Path,
) -> None:
    """
    Apply a single migration.
    
    Args:
        conn: Database connection.
        migration_path: Path to migration SQL file.
    """
    migration_name = migration_path.name
    
    print(f"Applying migration: {migration_name}")
    
    # Read and execute migration
    sql = migration_path.read_text()
    
    async with conn.transaction():
        await conn.execute(sql)
        await conn.execute(
            "INSERT INTO _migrations (name) VALUES ($1)",
            migration_name,
        )
    
    print(f"  ✓ Applied: {migration_name}")


async def run_migrations() -> None:
    """Run all pending migrations."""
    print(f"Connecting to database...")
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        # Get applied migrations
        applied = await get_applied_migrations(conn)
        print(f"Already applied: {len(applied)} migrations")
        
        # Get all migration files
        if not MIGRATIONS_DIR.exists():
            print(f"Migrations directory not found: {MIGRATIONS_DIR}")
            return
        
        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        
        if not migration_files:
            print("No migration files found")
            return
        
        # Apply pending migrations
        pending = [
            f for f in migration_files
            if f.name not in applied
        ]
        
        if not pending:
            print("All migrations already applied")
            return
        
        print(f"Pending migrations: {len(pending)}")
        
        for migration_path in pending:
            await apply_migration(conn, migration_path)
        
        print(f"\n✓ All migrations applied successfully")
        
    finally:
        await conn.close()


async def rollback_migration(migration_name: str) -> None:
    """
    Rollback a specific migration.
    
    Note: This only removes the migration from tracking table.
    You need to manually revert database changes.
    
    Args:
        migration_name: Name of migration to rollback.
    """
    print(f"Rolling back migration: {migration_name}")
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        result = await conn.execute(
            "DELETE FROM _migrations WHERE name = $1",
            migration_name,
        )
        
        if "DELETE 1" in result:
            print(f"  ✓ Rolled back: {migration_name}")
        else:
            print(f"  ! Migration not found: {migration_name}")
    finally:
        await conn.close()


def main() -> None:
    """Main entry point."""
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "rollback" and len(sys.argv) > 2:
            migration_name = sys.argv[2]
            asyncio.run(rollback_migration(migration_name))
        else:
            print(f"Unknown command: {command}")
            print("Usage:")
            print("  python main.py           # Run all migrations")
            print("  python main.py rollback <migration_name>  # Rollback migration")
            sys.exit(1)
    else:
        asyncio.run(run_migrations())


if __name__ == "__main__":
    main()
