@echo off
echo ========================================================
echo        TradePulse Master-Slave Copier Setup
echo ========================================================
echo.
echo Make sure you have activated your virtual environment!
echo For example: .\venv\Scripts\activate
echo.

echo [1/3] Installing/verifying requirements...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install requirements.
    exit /b %errorlevel%
)
echo [OK] Requirements installed.
echo.

echo [2/3] Running Database Migrations for Copier...
python scripts\migrate_copier.py
if %errorlevel% neq 0 (
    echo [ERROR] Migration failed. Make sure your database is running and .env is correct.
    exit /b %errorlevel%
)
echo [OK] Migration complete.
echo.

echo [3/3] Setting up Master and Slave accounts...
python scripts\setup_copier.py
if %errorlevel% neq 0 (
    echo [ERROR] Account setup failed.
    exit /b %errorlevel%
)
echo.

echo ========================================================
echo SETUP COMPLETE!
echo.
echo To run the system, open THREE separate PowerShell windows
echo and run the following commands (after activating venv):
echo.
echo 1. Main Server (Background sync):
echo    python run.py
echo.
echo 2. Master Copier:
echo    python workers\copier_master.py "C:\Program Files\MetaTrader 5\terminal64.exe" 1
echo.
echo 3. Slave Copier:
echo    python workers\copier_slave.py "C:\Program Files\MT5slave\terminal64.exe" 1 1.0
echo ========================================================
pause
