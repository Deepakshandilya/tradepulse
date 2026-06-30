import socketio
import time

# Create a Socket.IO client
sio = socketio.Client(logger=True, engineio_logger=True)

@sio.event
def connect():
    print("\n✅ [CLIENT] Connected to TradePulse WebSockets!")
    
    # 1. Subscribe to symbols
    print("📡 [CLIENT] Subscribing to EURUSD and GBPUSD...")
    sio.emit('subscribe', {'symbols': ['EURUSD', 'GBPUSD']})

@sio.event
def market_data(data):
    # This triggers every time the server sends a new price
    print(f"📈 [TICK] {data['symbol']} | Bid: {data['bid']} | Ask: {data['ask']}")

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
