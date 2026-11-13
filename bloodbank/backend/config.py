import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "bloodbank.db")

HTTP_PORT = int(os.environ.get("BB_HTTP_PORT", os.environ.get("PORT", "8500")))
HTTP_HOST = os.environ.get("BB_HOST", "127.0.0.1")

os.makedirs(DATA_DIR, exist_ok=True)
