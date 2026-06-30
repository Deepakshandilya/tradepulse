"""
TradePulse — Entry Point
Run with:  python run.py
"""

import eventlet
eventlet.monkey_patch()          # Must be first — patches stdlib for async I/O

from app import create_app, socketio

app = create_app()

if __name__ == "__main__":
    print("🚀  TradePulse server starting on http://localhost:5000")
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=app.config["DEBUG"],
        use_reloader=False,       # Reloader causes APScheduler to start twice
    )
