# TradePulse Trade Copier — How to Run

## Overview

The Trade Copier mirrors every trade opened on the **Master** account (`5052406468`) to the **Slave** account (`109043772`) automatically.

| Account | Role | MT5 Terminal |
|---|---|---|
| 5052406468 | MASTER | `C:\Program Files\MetaTrader 5\terminal64.exe` |
| 109043772 | SLAVE | `C:\Program Files\MT5slave\terminal64.exe` |

---

## Prerequisites Checklist

Before running, make sure:

- [ ] **Both MT5 terminals are open** and logged into their respective accounts.
- [ ] **Redis is running** as a Windows service (installed via MSI). Do **NOT** run `redis-server` manually — it is already running in the background. You can verify by opening `services.msc` and checking that **Redis** service status is **Running**.
- [ ] The **TradePulse venv** has been set up (`pip install -r requirements.txt`).

---

## Step-by-Step: Running the Copier

Open **two separate PowerShell windows** in the TradePulse directory.

### Window 1 — Start the Master Worker

The Master worker monitors account `5052406468` for new trades.

```powershell
cd C:\Users\deeps\OneDrive\Desktop\tradepulse
.\venv\Scripts\python.exe workers\copier_master.py "C:\Program Files\MetaTrader 5\terminal64.exe" 1
```

Expected output:
```
[INFO] Connecting to Master Terminal: C:\Program Files\MetaTrader 5\terminal64.exe
[INFO] Connected to Redis.
[INFO] Master 1 monitoring started...
```

---

### Window 2 — Start the Slave Worker

The Slave worker listens for signals and copies trades to account `109043772`.

```powershell
cd C:\Users\deeps\OneDrive\Desktop\tradepulse
.\venv\Scripts\python.exe workers\copier_slave.py "C:\Program Files\MT5slave\terminal64.exe" 1 1.0
```

Expected output:
```
[INFO] Connecting to Slave Terminal: C:\Program Files\MT5slave\terminal64.exe
[INFO] Connected to Redis.
[INFO] Slave listening for signals from Master 1 with multiplier 1.0...
```

---

## Test It

1. Open the Master MT5 terminal (`5052406468`).
2. Place a BUY or SELL trade on any symbol (e.g. EURUSD, 0.01 lot).
3. Within ~500ms you should see in the **Master window**:
   ```
   [INFO] Published OPEN signal: {'action': 'OPEN', 'symbol': 'EURUSD', ...}
   ```
4. And in the **Slave window**:
   ```
   [INFO] Received signal: {'action': 'OPEN', 'symbol': 'EURUSD', ...}
   [INFO] Executing BUY on EURUSD with volume 0.01...
   [INFO] Trade executed successfully: Ticket 12345678
   ```
5. Check the Slave MT5 terminal — the same trade should now be open!

---

## Volume Multiplier

The `1.0` at the end of the Slave command is the **volume multiplier**.

| Value | Effect |
|---|---|
| `1.0` | Copy exact same volume as Master |
| `0.5` | Copy half the volume |
| `2.0` | Copy double the volume |

To change it, restart the Slave worker with a different value:
```powershell
.\venv\Scripts\python.exe workers\copier_slave.py "C:\Program Files\MT5slave\terminal64.exe" 1 2.0
```

---

## Stopping the Copier

Press `Ctrl + C` in either PowerShell window to stop the respective worker.
Stopping the Master means no new signals will be sent.
Stopping the Slave means trades will no longer be copied.

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `Redis connection failed: unknown command HELLO` | Redis server is v5 but Python redis client is v8 | Run: `.\venv\Scripts\python.exe -m pip install "redis<4.0"` |
| `bind: An operation was attempted on something that is not a socket` | Redis is already running as a Windows service | This is normal — do NOT run `redis-server` again |
| `initialize() failed` | MT5 terminal is not open | Open the MT5 terminal and log in before running the worker |
| `Symbol not found` | Symbol not available on that broker | Make sure both accounts are on the same broker (MetaQuotes-Demo) |
