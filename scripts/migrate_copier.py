"""
Migration: Add Trade Copier columns to broker_accounts table.
Run once: python migrate_copier.py
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db

app = create_app()

with app.app_context():
    from sqlalchemy import text, inspect

    inspector = inspect(db.engine)
    existing_cols = [c["name"] for c in inspector.get_columns("broker_accounts")]

    migrations = [
        ("role",              "ALTER TABLE broker_accounts ADD COLUMN role VARCHAR(20) DEFAULT 'STANDALONE'"),
        ("master_account_id", "ALTER TABLE broker_accounts ADD COLUMN master_account_id INTEGER REFERENCES broker_accounts(id)"),
        ("volume_multiplier", "ALTER TABLE broker_accounts ADD COLUMN volume_multiplier FLOAT DEFAULT 1.0"),
        ("terminal_path",     "ALTER TABLE broker_accounts ADD COLUMN terminal_path VARCHAR(255)"),
    ]

    for col_name, sql in migrations:
        if col_name not in existing_cols:
            db.session.execute(text(sql))
            print(f"  Added column: {col_name}")
        else:
            print(f"  Column already exists, skipping: {col_name}")

    db.session.commit()
    print("\nMigration complete.")
