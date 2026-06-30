# TradePulse 📈

A real-time **Trading CRM backend** built with Python, Flask, and MetaTrader 5.  
Syncs trade history, calculates commissions, and streams live market data via WebSockets.

---

## Features

- 🔄 **MT5 Trade Sync** — Auto-syncs closed deals from MetaTrader 5, avoids duplicates
- 💰 **Commission Engine** — Calculates $5/lot fees, stores results, notifies clients in real-time
- 📡 **Live Market Data** — Streams bid/ask prices every second via WebSocket
- 🔔 **Event Notifications** — Emits `commission_created` events on new commissions
- 🗄️ **MySQL Database** — Users, Broker Accounts, Trades, Commissions with proper relations
- ⚙️ **Background Sync** — APScheduler runs trade sync every 60 seconds automatically

---

## Tech Stack

| Layer         | Technology                              |
|---------------|-----------------------------------------|
| API Framework | Flask 3, Blueprints                     |
| Database      | MySQL + Flask-SQLAlchemy                |
| WebSockets    | Flask-SocketIO + Eventlet               |
| MT5 Bridge    | MetaTrader5 Python package (Windows)    |
| Scheduler     | APScheduler                             |

---

## Project Structure

```
tradepulse/
├── docs/                   # Planning documents
├── models/                 # SQLAlchemy ORM models
├── routes/                 # Flask REST API blueprints
├── services/               # MT5 service, commission engine
├── workers/                # APScheduler background jobs
├── sockets/                # SocketIO event handlers
├── live_data/              # Live market data broadcaster
├── utils/                  # Shared helpers
├── config.py               # Centralised configuration
├── app.py                  # Flask app factory
└── run.py                  # Entry point
```

---

## Setup

### 1. Prerequisites
- Python 3.11+
- MySQL running locally
- MetaTrader 5 terminal installed and logged in (Windows only)

### 2. Clone & Install

```bash
git clone https://github.com/your-username/tradepulse.git
cd tradepulse

python -m venv venv
venv\Scripts\activate        # Windows

pip install -r requirements.txt
```

### 3. Configure Environment

```bash
copy .env.example .env
# Edit .env with your MySQL credentials and MT5 login details
```

### 4. Create the Database

```sql
CREATE DATABASE tradepulse CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Tables are created automatically on first run via `db.create_all()`.

### 5. Run

```bash
python run.py
```

Server starts at `http://localhost:5000`.

---

## REST API Reference

**Interactive Documentation (Swagger UI)**  
Once the server is running, you can view the full OpenAPI 3.0 documentation and test endpoints interactively by visiting:  
👉 **`http://localhost:5000/apidocs`**

### Users

| Method | Endpoint            | Description         |
|--------|---------------------|---------------------|
| POST   | `/api/users`        | Create a user       |
| GET    | `/api/users`        | List all users      |
| GET    | `/api/users/<id>`   | Get user by ID      |
| DELETE | `/api/users/<id>`   | Delete a user       |

**Create user example:**
```bash
curl -X POST http://localhost:5000/api/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com"}'
```

### Broker Accounts

| Method | Endpoint                   | Description               |
|--------|----------------------------|---------------------------|
| POST   | `/api/accounts`            | Add account to a user     |
| GET    | `/api/accounts/<user_id>`  | List accounts for user    |
| DELETE | `/api/accounts/<id>`       | Remove an account         |

**Add account example:**
```bash
curl -X POST http://localhost:5000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "account_no": "123456", "broker_name": "DemoFX"}'
```

### Trades

| Method | Endpoint                        | Description               |
|--------|---------------------------------|---------------------------|
| POST   | `/api/trades/sync/<account_id>` | Manual MT5 sync trigger   |
| GET    | `/api/trades/<account_id>`      | List trades for account   |

### Commissions

| Method | Endpoint                              | Description                    |
|--------|---------------------------------------|--------------------------------|
| GET    | `/api/commissions/<account_id>`       | List commissions for account   |
| GET    | `/api/commissions/trade/<trade_id>`   | Commission for a specific trade|

---

## WebSocket Guide

Connect with any Socket.IO client:

```python
import socketio
sio = socketio.Client()

@sio.on("market_data")
def on_data(data):
    print(f"{data['symbol']}  bid={data['bid']}  ask={data['ask']}")

@sio.on("commission_created")
def on_commission(data):
    print(f"Commission! Trade #{data['trade_id']}  ${data['amount_usd']}")

sio.connect("http://localhost:5000")
sio.emit("subscribe", {"symbols": ["EURUSD", "GBPUSD", "XAUUSD"]})
sio.wait()
```

### Events

| Event                | Direction       | Description                         |
|----------------------|-----------------|-------------------------------------|
| `subscribe`          | Client → Server | Subscribe to symbol price stream    |
| `unsubscribe`        | Client → Server | Unsubscribe from symbols            |
| `market_data`        | Server → Client | Live bid/ask tick (every 1 second)  |
| `commission_created` | Server → Client | Fired when a new commission is saved|

---

## Commission Rule

```
commission = volume (lots) × $5.00
```

Commissions are idempotent — running the engine twice for the same trade will not create duplicates.

---

## Development Notes

- **MT5 not installed?** The `MT5Service` detects this and runs in stub mode (returns empty data) — the rest of the app works normally.
- **APScheduler + debug mode**: `use_reloader=False` is set in `run.py` to prevent the scheduler from starting twice.
- **Duplicate trades**: Deduplicated by the MT5 `ticket` field (unique index on the `trades` table).

---

## Architecture Constraints

**The MT5 Single-Connection Limit:**
The official `MetaTrader5` Python library can only maintain **one global connection** to the active terminal at a time. Therefore, the background `sync_worker.py` is configured to **only sync the account specified in your `.env` file**. 

If you wish to scale this to a Multi-Account "Trade Copier", please see the advanced architecture plan located in `docs/master_slave_architecture.md`.

---

## Testing

A suite of manual integration tests is provided in the `tests/` directory to verify core functionality against a live MT5 terminal.

```bash
python tests/test_feature1.py   # Live Market Data WebSocket
python tests/test_feature2.py   # Database Models & ORM
python tests/test_feature3.py   # Manual Trade Sync & Deduplication
python tests/test_feature4.py   # Commission Calculation Engine
```
