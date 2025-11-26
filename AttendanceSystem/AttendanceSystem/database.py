import sqlite3
import os
from config import DB_PATH
import hashlib

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Students table
    c.execute('''CREATE TABLE IF NOT EXISTS students
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  student_id TEXT UNIQUE,
                  face_encoding_path TEXT)''')
                 
    # Attendance table
    c.execute('''CREATE TABLE IF NOT EXISTS attendance
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  student_id TEXT,
                  date DATE,
                  lecture_number INTEGER,
                  timestamp DATETIME,
                  UNIQUE(student_id, date, lecture_number))''')  # Added unique constraint
                  
    # Admin credentials
    c.execute('''CREATE TABLE IF NOT EXISTS admins
                 (username TEXT PRIMARY KEY,
                  password TEXT)''')
    
    # Insert default admin with hashed password
    default_password = hashlib.sha256("admin123".encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO admins VALUES (?, ?)", ('admin', default_password))
    
    # Create indexes for better performance
    c.execute("CREATE INDEX IF NOT EXISTS idx_attendance_student_id ON attendance(student_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_attendance_lecture ON attendance(lecture_number)")
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    print("Database initialized successfully!")