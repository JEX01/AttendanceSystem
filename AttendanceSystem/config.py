import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, 'db')
DB_PATH = os.path.join(DB_DIR, 'attendance.db')
FACE_ENCODINGS_DIR = os.path.join(BASE_DIR, 'face_encodings')
REPORTS_DIR = os.path.join(BASE_DIR, 'reports')
LOG_DIR = os.path.join(BASE_DIR, 'logs')  # Logging directory

# Create directories if they don't exist
os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(FACE_ENCODINGS_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
