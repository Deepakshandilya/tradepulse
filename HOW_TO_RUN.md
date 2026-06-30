# TradePulse — Master/Slave Copier Setup Guide

This guide explains how to set up and run the TradePulse Master-Slave Trade Copier. The copier architecture uses **Redis Pub/Sub** to send trade signals from a Master MT5 terminal instantly to one or more Slave MT5 terminals.

---

## 1. Prerequisites

Before starting, ensure you have the following installed and running:
1. **Python 3.10+** (and a virtual environment created with `python -m venv venv`)
2. **MySQL** (Running locally on `localhost:3306`)
3. **Redis** (Running as a Windows Service on `localhost:6379`)
4. **Two MT5 Terminals installed** in separate folders (e.g. `C:\Program Files\MetaTrader 5` and `C:\Program Files\MT5slave`)

> **IMPORTANT:** In both MT5 terminals, ensure you have **AutoTrading enabled** (the green ✅ button in the top toolbar).

---

## 2. Configuration (`.env`)

Ensure your `.env` file exists and points to the **Master** account credentials. Do NOT point it to the Slave account. The background sync worker uses this to fetch history for the Master.

```ini
DB_URI=mysql+pymysql://root:root@localhost/tradepulse

# MetaTrader 5 (MASTER Account)
MT5_LOGIN=5052406468
MT5_PASSWORD=your_password
MT5_SERVER=MetaQuotes-Demo

REDIS_URL=redis://localhost:6379/0
```

---

## 3. One-Click Setup

To install dependencies, run database migrations, and seed the Master and Slave accounts in the database, simply run the batch script:

```powershell
# Make sure your virtual environment is activated first!
.\venv\Scripts\activate

# Run the setup script
.\setup_copier.bat
```

*(If you prefer to run it manually, execute: `python scripts\migrate_copier.py` followed by `python scripts\setup_copier.py`).*

---

## 4. Running the System

The system requires three separate processes running simultaneously. Open **three separate PowerShell windows**, activate your virtual environment in each (`.\venv\Scripts\activate`), and run:

### Window 1: Main Server & Background Jobs
This runs the Flask API, WebSockets, and the APScheduler which fetches closed trade history for the Master account every 60 seconds.
```powershell
python run.py
```

### Window 2: Master Copier
This connects to the Master MT5 terminal. It polls for new open/closed trades every 500ms and publishes signals to Redis.
```powershell
python workers\copier_master.py "C:\Program Files\MetaTrader 5\terminal64.exe" 1
```

### Window 3: Slave Copier
This listens to Redis for trade signals and instantly executes them on the Slave MT5 terminal. It also writes slave trades directly to the database so they appear instantly without waiting for a sync cycle.
```powershell
python workers\copier_slave.py "C:\Program Files\MT5slave\terminal64.exe" 1 1.0
```
*(The arguments are: `Terminal Path`, `Master Account ID`, and `Volume Multiplier`).*

---

## Troubleshooting

- **Redis Error (`unknown command HELLO`)**: Your Python `redis` package version is too new for your Redis 5.x server. Ensure you ran `pip install -r requirements.txt` which pins `redis<4.0`.
- **Order send failed, retcode=10027**: "AutoTrading disabled by client". Click the AutoTrading button in the MT5 terminal toolbar to turn it green.
- **Trades not showing for Slave**: Make sure you aren't clicking "Manual Sync" for the slave account in the web dashboard. Manual sync is only supported for the Master terminal. Slave trades are written to the database automatically at the moment of execution.
