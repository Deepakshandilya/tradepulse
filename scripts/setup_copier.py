"""
Setup Copier Accounts

Sets account 5052406468 as MASTER and 109043772 as SLAVE,
with the terminal paths provided.

Run once: python setup_copier.py
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db

app = create_app()

with app.app_context():
    from models.broker_account import BrokerAccount

    master = BrokerAccount.query.filter_by(account_no="5052406468").first()
    slave  = BrokerAccount.query.filter_by(account_no="109043772").first()

    if not master:
        print("ERROR: Master account 5052406468 not found in DB.")
        sys.exit(1)
    if not slave:
        print("ERROR: Slave account 109043772 not found in DB.")
        sys.exit(1)

    # Configure MASTER
    master.role           = "MASTER"
    master.terminal_path  = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    master.volume_multiplier = 1.0

    # Configure SLAVE — linked to master
    slave.role              = "SLAVE"
    slave.master_account_id = master.id
    slave.terminal_path     = r"C:\Program Files\MT5slave\terminal64.exe"
    slave.volume_multiplier = 1.0   # Change to 2.0 if you want to double the lot size

    db.session.commit()

    print("\n[OK] Copier accounts configured!")
    print(f"   MASTER  -> ID={master.id}  Account={master.account_no}  Terminal={master.terminal_path}")
    print(f"   SLAVE   -> ID={slave.id}   Account={slave.account_no}   Terminal={slave.terminal_path}")
    print(f"   Volume Multiplier: {slave.volume_multiplier}x")
    print(f"\n   To run Master worker:")
    print(f"   .\\venv\\Scripts\\python.exe workers\\copier_master.py \"{master.terminal_path}\" {master.id}")
    print(f"\n   To run Slave worker:")
    print(f"   .\\venv\\Scripts\\python.exe workers\\copier_slave.py \"{slave.terminal_path}\" {master.id} {slave.volume_multiplier}")
