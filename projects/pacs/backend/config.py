import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DICOM_DIR = os.path.join(DATA_DIR, "dicom")
DB_PATH = os.path.join(DATA_DIR, "pacs.db")

HTTP_PORT = int(os.environ.get("PACS_HTTP_PORT", "8000"))
DICOM_PORT = int(os.environ.get("PACS_DICOM_PORT", "11112"))
AE_TITLE = os.environ.get("PACS_AE_TITLE", "OPENPACS")

os.makedirs(DICOM_DIR, exist_ok=True)
