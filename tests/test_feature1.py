import sys
import io
import socketio
import time
from datetime import datetime

# Force UTF-8 encoding for Windows console to support emojis, with line_buffering so it prints instantly
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf8', line_buffering=True)

# Create a Socket.IO client (logging disabled for clean output)
sio = socketio.Client(logger=False, engineio_logger=False)

# ANSI Colors for terminal output
RESET = '\033[0m'
BID_COLOR = '\033[91m'  # Red
ASK_COLOR = '\033[92m'  # Green
SYMBOL_COLORS = {
    'EURUSD': '\033[96m',  # Cyan
    'GBPUSD': '\033[95m',  # Magenta
    'XAUUSD': '\033[93m',  # Yellow
    'USDCHF': '\033[94m',  # Blue
}

@sio.event
def connect():
    print("\n✅ [CLIENT] Connected to TradePulse WebSockets!")
    
    # 1. Subscribe to symbols
    print("📡 [CLIENT] Subscribing to EURUSD and GBPUSD...")
    sio.emit('subscribe', {'symbols': ['EURUSD', 'GBPUSD', 'USDINR']})

@sio.event
def market_data(data):
    # This triggers every time the server sends a new price
    now = datetime.now().strftime("%H:%M:%S")
    sym = data['symbol']
    sym_color = SYMBOL_COLORS.get(sym, '\033[97m') # Default White
    
    print(f"[{now}] {sym_color}{sym:<8}{RESET} | {BID_COLOR}Bid: {data['bid']:<8}{RESET} | {ASK_COLOR}Ask: {data['ask']:<8}{RESET}")

@sio.event
def disconnect():
    print("\n❌ [CLIENT] Disconnected from server")

if __name__ == '__main__':
    print("⏳ Connecting to http://localhost:5000...")
    sio.connect('http://localhost:5000')
    
    try:
        # Keep the script running to listen for ticks
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sio.disconnect()
        print("Test ended.")
