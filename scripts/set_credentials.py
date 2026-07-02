"""
Helper script to update MT5 credentials for an existing TradePulse BrokerAccount.
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from utils.encryption import encrypt_password

def update_account(account_id: int, login: int, password: str, server: str):
    app = create_app(start_workers=False)
    with app.app_context():
        from models.broker_account import BrokerAccount
        account = BrokerAccount.query.get(account_id)
        if not account:
            print(f"Error: Account with ID {account_id} not found.")
            return

        account.login = login
        account.password_encrypted = encrypt_password(password)
        account.server = server
        
        db.session.commit()
        print(f"Successfully updated credentials for account ID {account_id} (Login: {login}).")

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python set_credentials.py <account_id> <login> <password> <server>")
        print("Example: python set_credentials.py 3 109043772 \"-a5zDuAl\" \"MetaQuotes-Demo\"")
        sys.exit(1)

    account_id = int(sys.argv[1])
    login = int(sys.argv[2])
    password = sys.argv[3]
    server = sys.argv[4]

    update_account(account_id, login, password, server)
