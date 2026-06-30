# TradePulse 📈

TradePulse is a two-part trading system built with Python, Flask, and MetaTrader 5:

1. **Trading CRM:** A real-time backend that auto-syncs trade history, calculates commissions, and streams live market data via WebSockets.
2. **Master-Slave Trade Copier:** A low-latency system that instantly mirrors trades from a Master MT5 terminal to one or more Slave MT5 terminals using Redis.

---

## 🏗️ Architecture

Because the official `MetaTrader5` Python package can only connect to **one terminal per process**, the system is split into independent workers communicating via a central database and Redis Pub/Sub.

### 1. The Main Server (CRM)
Runs the Flask API and a background scheduler (APScheduler).
- **Responsibility:** Syncs closed trade history for the **Master** account every 60 seconds, calculates commissions, and streams live prices to web clients.
- **Connection:** Connects only to the Master terminal defined in `.env`.

### 2. Copier Master Worker
A standalone Python process.
- **Responsibility:** Polls the Master MT5 terminal every 500ms. When a trade is opened or closed, it publishes a JSON signal to Redis.

### 3. Copier Slave Worker
A standalone Python process.
- **Responsibility:** Listens to Redis. When it receives a signal, it instantly executes the trade on the Slave MT5 terminal. It then writes the executed trade directly into the TradePulse database (so the trade appears in the CRM immediately without waiting for the 60-second sync).

```mermaid
graph TD
    A[run.py (Main Server)] -->|Syncs History every 60s| DB[(MySQL Database)]
    A -->|Reads| MasterTerminal(Master MT5)
    
    B[copier_master.py] -->|Polls every 500ms| MasterTerminal
    B -->|Publishes OPEN/CLOSE| Redis((Redis))
    
    C[copier_slave.py] -->|Subscribes| Redis
    C -->|Executes Trades| SlaveTerminal(Slave MT5)
    C -->|Writes slave trades instantly| DB
```

---

## 🚀 One-Click Setup

### Prerequisites
1. **Python 3.11+**
2. **MySQL** (Running locally on `localhost:3306`)
3. **Redis** (Running as a Windows Service on `localhost:6379`)
4. **Two MT5 Terminals installed** in separate folders (e.g. `C:\Program Files\MetaTrader 5` and `C:\Program Files\MT5slave`).
5. **AutoTrading Enabled** in both terminals (the green ✅ button in the MT5 top toolbar).

### 1. Configure `.env`
Copy `.env.example` to `.env` and fill in your **Master** account details. Do NOT put the Slave account here.

```ini
DB_URI=mysql+pymysql://root:root@localhost/tradepulse

# MetaTrader 5 (MASTER Account)
MT5_LOGIN=5052406468
MT5_PASSWORD=your_password
MT5_SERVER=MetaQuotes-Demo

REDIS_URL=redis://localhost:6379/0
```

### 2. Run the Installer
Create a virtual environment and run the provided setup script. This will install all dependencies, run the database migrations, and configure your Master and Slave accounts in the database.

```powershell
python -m venv venv
.\venv\Scripts\activate

.\setup_copier.bat
```

---

## 🏃‍♂️ How to Run

Because of the single-terminal limit, the system requires **three separate processes** running simultaneously. 

Open **three separate PowerShell windows**, activate your virtual environment in each (`.\venv\Scripts\activate`), and run:

### Window 1: Main Server (CRM)
```powershell
python run.py
```
*(Starts the Web API on `http://localhost:5000` and background trade sync).*

### Window 2: Master Copier
```powershell
python workers\copier_master.py "C:\Program Files\MetaTrader 5\terminal64.exe" 1
```
*(Arguments: `<Terminal Path>` `<Master DB Account ID>`)*

### Window 3: Slave Copier
```powershell
python workers\copier_slave.py "C:\Program Files\MT5slave\terminal64.exe" 1 1.0
```
*(Arguments: `<Terminal Path>` `<Master DB Account ID>` `<Volume Multiplier>`)*

---

## 🛠️ API & Integrations

**Interactive Documentation (Swagger UI)**  
Once the main server is running, view the full OpenAPI 3.0 documentation at:  
👉 **`http://localhost:5000/apidocs`**

### REST API Highlights
- `POST /api/users` — Create users
- `POST /api/accounts` — Link MT5 accounts to users
- `GET /api/trades/<account_id>` — List trades
- `GET /api/commissions/<account_id>` — List commissions ($5/lot fee automatically calculated)

### WebSockets
Connect a Socket.IO client to `http://localhost:5000` to receive:
- `market_data` — Live bid/ask ticks every 1 second
- `commission_created` — Real-time alerts when a new commission is earned

---

## ⚠️ Troubleshooting

- **Order send failed, retcode=10027**: "AutoTrading disabled by client". Click the AutoTrading button in the MT5 terminal toolbar to turn it green.
- **Order send failed, retcode=10030**: "Unsupported filling mode". The workers auto-detect the supported filling mode, but ensure the symbol you are trading is actually available and visible in the Slave's Market Watch.
- **Redis Connection Error**: Ensure Redis is running as a Windows Service (`services.msc` -> Redis).
- **Cannot Manually Sync Slave Trades**: This is intentional. The Main Server is only connected to the Master terminal. Slave trades are written to the database automatically at the exact moment of execution by the `copier_slave.py` worker.
