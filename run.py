"""
TradePulse — Entry Point
Run with:  python run.py
"""

import eventlet
eventlet.monkey_patch()          # Must be first — patches stdlib for async I/O

import logging
import sys

class ColoredFormatter(logging.Formatter):
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    RESET = "\033[0m"
    DIM = "\033[2m"

    def format(self, record):
        if record.levelno >= logging.ERROR:
            color = self.RED
        elif record.levelno >= logging.WARNING:
            color = self.YELLOW
        elif record.levelno >= logging.INFO:
            color = self.GREEN
        else:
            color = self.DIM
            
        time_str = f"{self.DIM}%(asctime)s{self.RESET}"
        level_str = f"{color}[%(levelname)s]{self.RESET}"
        name_str = f"{self.CYAN}%(name)s{self.RESET}"
        msg_str = f"{color}%(message)s{self.RESET}"
        
        formatter = logging.Formatter(f"{time_str} {level_str} {name_str}: {msg_str}", datefmt="%H:%M:%S")
        return formatter.format(record)

# Remove any existing handlers
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(ColoredFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])

from app import create_app, socketio

app = create_app()

if __name__ == "__main__":
    print("TradePulse server starting on http://localhost:5000")
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=app.config["DEBUG"],
        use_reloader=False,       # Reloader causes APScheduler to start twice
    )
