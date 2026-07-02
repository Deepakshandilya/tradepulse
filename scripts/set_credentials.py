"""
Helper script to update MT5 credentials for an existing TradePulse BrokerAccount.
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from utils.encryption import encrypt_password

def update_account(account_id: int, password: str, server: str):
    app = create_app(start_workers=False)
    with app.app_context():
        from models.broker_account import BrokerAccount
        account = db.session.get(BrokerAccount, account_id)
        if not account:
            print(f"Error: Account with ID {account_id} not found.")
            return

        # Automatically infer the login from the existing account_no
        login = int(account.account_no)
        account.login = login
        account.password_encrypted = encrypt_password(password)
        account.server = server
        
        db.session.commit()
        print(f"Successfully updated credentials for account ID {account_id} (Login: {login}).")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python set_credentials.py <account_id> <password> <server>")
        print("Example: python set_credentials.py 3 \"-a5zDuAl\" \"MetaQuotes-Demo\"")
        sys.exit(1)

    account_id = int(sys.argv[1])
    password = sys.argv[2]
    server = sys.argv[3]

    update_account(account_id, password, server)
