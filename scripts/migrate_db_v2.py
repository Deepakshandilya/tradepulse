import os
import sys

# Add the project root to sys.path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from sqlalchemy import text

def run_migration():
    """
    Adds sl, tp to trades table.
    Adds copy_sl_tp, max_drawdown, is_active to broker_accounts table.
    """
    app = create_app(start_workers=False)
    with app.app_context():
        try:
            print("Adding 'sl' and 'tp' columns to 'trades' table...")
            db.session.execute(text("ALTER TABLE trades ADD COLUMN sl FLOAT DEFAULT NULL"))
            db.session.execute(text("ALTER TABLE trades ADD COLUMN tp FLOAT DEFAULT NULL"))
        except Exception as e:
            print(f"Skipped adding trades columns (might already exist): {e}")

        try:
            print("Adding 'copy_sl_tp', 'max_drawdown', 'is_active' columns to 'broker_accounts' table...")
            db.session.execute(text("ALTER TABLE broker_accounts ADD COLUMN copy_sl_tp BOOLEAN DEFAULT TRUE"))
            db.session.execute(text("ALTER TABLE broker_accounts ADD COLUMN max_drawdown FLOAT DEFAULT NULL"))
            db.session.execute(text("ALTER TABLE broker_accounts ADD COLUMN is_active BOOLEAN DEFAULT TRUE"))
        except Exception as e:
            print(f"Skipped adding broker_accounts columns (might already exist): {e}")

        db.session.commit()
        print("Migration v2 completed successfully!")

if __name__ == "__main__":
    run_migration()
