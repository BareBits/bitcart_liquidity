# This is a concept for a dashboard to display various things. It currently does a whole lot of nothing.
from flask import Flask,render_template
from classes import BitcartAPI
import asyncio,liquidityhelper
from config import *
import logging,sys
from logging.handlers import RotatingFileHandler
import queue
app = Flask(__name__)
BITCART_URL = "http://127.0.0.1/api"  # Replace with your Bitcart URL

# Setup logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
main_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
)

# Save logs to file
file_handler = RotatingFileHandler('dashboard.log', maxBytes=10000000, backupCount=5)
file_handler.setLevel(logging.WARNING)
file_handler.setFormatter(main_formatter)
logger.addHandler(file_handler)

# Do queued logging to increase responsiveness
log_queue = queue.Queue(250)
# Configure the downstream console handler
console_handler = logging.StreamHandler(stream=sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(main_formatter)
# Create and start the QueueListener with the console handler
listener = logging.handlers.QueueListener(log_queue, console_handler)
listener.start()
queue_handler = logging.handlers.QueueHandler(log_queue)
# Configure the logger to use the QueueHandler
logger.addHandler(queue_handler)
@app.route('/')
def hello_world():
    return 'Hello, World!'

@app.route('/dashboard')
async def dashboard():
    user_name = "Alice"
    items = ["Apple", "Banana", "Orange"]
    logger.info("Initializing API...")
    try:
        api = BitcartAPI(BITCART_URL, AUTH_TOKEN)
        # Check authentication
        auth_result = await api.is_authenticated()
        if auth_result:
            print("✅ API client initialized with authentication token!")
        else:
            print("⚠️ No authentication token provided, some endpoints may fail...")
            return('No auth token for API provided')
    except Exception as e:
        print(f"Error connecting to api {e}")
        return ('Errro connecting to API')
    return render_template('dashboard.html', name=user_name, item_list=items)

if __name__ == "__main__":
    app.run(debug=True, port=5788, threaded=True, use_reloader=False)