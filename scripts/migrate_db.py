"""
Migration script to add new columns to BrokerAccount and Trade models
and populate the Master account (id=1) and Slave account (id=3) from .env.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from sqlalchemy import text
from utils.encryption import encrypt_password
from config import Config

def upgrade_schema():
    app = create_app(start_workers=False)
    with app.app_context():
        # Using raw SQL to avoid dropping tables and losing data
        # Check if columns exist first (simple try/except for SQLite/MySQL)
        try:
            db.session.execute(text("ALTER TABLE broker_accounts ADD COLUMN login BIGINT;"))
            db.session.execute(text("ALTER TABLE broker_accounts ADD COLUMN password_encrypted BLOB;"))
            db.session.execute(text("ALTER TABLE broker_accounts ADD COLUMN server VARCHAR(100);"))
            print("Added login, password_encrypted, server to broker_accounts.")
        except Exception as e:
            print("Columns might already exist on broker_accounts:", e)

        try:
            # Need to drop unique constraint if we want to add UNIQUE to terminal_path? 
            # Or we can just leave it as is if it fails.
            db.session.execute(text("ALTER TABLE broker_accounts ADD CONSTRAINT uq_terminal_path UNIQUE(terminal_path);"))
            print("Added unique constraint to terminal_path.")
        except Exception as e:
            pass
            
        try:
            db.session.execute(text("ALTER TABLE trades ADD COLUMN master_ticket_id BIGINT;"))
            db.session.execute(text("CREATE INDEX ix_trades_master_ticket_id ON trades (master_ticket_id);"))
            db.session.execute(text("ALTER TABLE trades ADD COLUMN status VARCHAR(20) DEFAULT 'OPEN';"))
            print("Added master_ticket_id, status to trades.")
        except Exception as e:
            print("Columns might already exist on trades:", e)
            
        db.session.commit()
        
        print("Schema migration complete.")

def migrate_env_credentials():
    app = create_app(start_workers=False)
    with app.app_context():
        from models.broker_account import BrokerAccount
        
        # Populate Master account (Assume ID = 1 based on .env comments)
        master = BrokerAccount.query.get(1)
        if master:
            master.login = Config.MT5_LOGIN
            master.password_encrypted = encrypt_password(Config.MT5_PASSWORD)
            master.server = Config.MT5_SERVER
            db.session.commit()
            print(f"Updated Master account (ID=1) with credentials from .env. (Login: {master.login})")
        else:
            print("Master account (ID=1) not found in DB.")
            
        # The .env file has comments for account ID 3 (Slave)
        # MT5_LOGIN=109043772, MT5_PASSWORD=-a5zDuAl, MT5_SERVER=MetaQuotes-Demo
        slave = BrokerAccount.query.get(3)
        if slave:
            slave.login = 109043772
            slave.password_encrypted = encrypt_password("-a5zDuAl")
            slave.server = "MetaQuotes-Demo"
            db.session.commit()
            print(f"Updated Slave account (ID=3) with credentials. (Login: {slave.login})")
        else:
            print("Slave account (ID=3) not found in DB.")

if __name__ == "__main__":
    print("Running DB migrations...")
    upgrade_schema()
    migrate_env_credentials()
