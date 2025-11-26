import tkinter as tk
from tkinter import messagebox, simpledialog
import cv2
import face_recognition
import numpy as np
from PIL import Image, ImageTk
import os
import sqlite3
from datetime import datetime
import time
import logging
import hashlib
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from admin_panel import AdminPanel

# Paths
DB_PATH = "attendance.db"
FACE_ENCODINGS_DIR = "face_encodings"
REPORTS_DIR = "reports"
LOG_DIR = "logs"

# Create directories if missing
os.makedirs(FACE_ENCODINGS_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# Logging
logging.basicConfig(
    filename=os.path.join(LOG_DIR, 'attendance.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Database Initialization
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS students (
        student_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        face_encoding_path TEXT NOT NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT,
        date TEXT,
        lecture_number INTEGER,
        timestamp TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )''')

    # Add default admin if none exists
    c.execute("SELECT COUNT(*) FROM admins")
    if c.fetchone()[0] == 0:
        default_username = "admin"
        default_password = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute("INSERT INTO admins (username, password) VALUES (?, ?)",
                  (default_username, default_password))

    conn.commit()
    conn.close()

class AttendanceSystem:
    def __init__(self):
        init_db()
        self.root = tk.Tk()
        self.root.title("Attendance System")
        self.root.geometry("400x300")
        self.center_window()

        self.video_capture = None
        self.capture_active = False
        self.known_encodings = []
        self.known_student_ids = []
        self.load_encodings_cache()

        self.create_main_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.cleanup)
        self.root.mainloop()

    def center_window(self, window=None):
        win = window if window else self.root
        win.update_idletasks()
        width = win.winfo_width()
        height = win.winfo_height()
        x = (win.winfo_screenwidth() // 2) - (width // 2)
        y = (win.winfo_screenheight() // 2) - (height // 2)
        win.geometry(f'{width}x{height}+{x}+{y}')

    def cleanup(self):
        self.capture_active = False
        if hasattr(self, 'video_capture') and self.video_capture and self.video_capture.isOpened():
            self.video_capture.release()
        self.root.destroy()

    def load_encodings_cache(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT student_id, face_encoding_path FROM students")
            students = c.fetchall()
            conn.close()

            self.known_encodings = []
            self.known_student_ids = []
            for student_id, encoding_path in students:
                if os.path.exists(encoding_path):
                    encoding = np.load(encoding_path)
                    self.known_encodings.append(encoding)
                    self.known_student_ids.append(student_id)
            logging.info(f"Loaded {len(self.known_encodings)} face encodings")
        except Exception as e:
            logging.error(f"Error loading encodings cache: {str(e)}")
            messagebox.showerror("Error", "Failed to load face encodings")

    def create_main_ui(self):
        main_frame = tk.Frame(self.root)
        main_frame.pack(pady=50)

        tk.Label(main_frame, text="Attendance System", font=('Arial', 16)).pack(pady=10)

        tk.Button(main_frame, text="Admin Login", command=self.open_admin_login,
                  width=20, height=2).pack(pady=10)

        tk.Button(main_frame, text="Mark Attendance", command=self.scan_face,
                  width=20, height=2).pack(pady=10)

    def open_admin_login(self):
        self.login_window = tk.Toplevel(self.root)
        self.login_window.title("Admin Login")
        self.login_window.geometry("300x200")
        self.center_window(self.login_window)

        tk.Label(self.login_window, text="Username:").pack(pady=5)
        self.username_entry = tk.Entry(self.login_window)
        self.username_entry.pack(pady=5)

        tk.Label(self.login_window, text="Password:").pack(pady=5)
        self.password_entry = tk.Entry(self.login_window, show="*")
        self.password_entry.pack(pady=5)

        tk.Button(self.login_window, text="Login",
                  command=self.verify_admin).pack(pady=10)

    def verify_admin(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        try:
            hashed_password = hashlib.sha256(password.encode()).hexdigest()
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT * FROM admins WHERE username=? AND password=?", (username, hashed_password))
            admin = c.fetchone()
            conn.close()

            if admin:
                self.login_window.destroy()
                messagebox.showinfo("Login", "Admin login successful!")
                logging.info(f"Admin {username} logged in")
                # Open the AdminPanel
                AdminPanel(self.root, self)
            else:
                messagebox.showerror("Error", "Invalid credentials")
                logging.warning(f"Failed login attempt for username: {username}")
        except Exception as e:
            messagebox.showerror("Error", f"Login failed: {str(e)}")
            logging.error(f"Admin login error: {str(e)}")

    def add_student(self):
        add_window = tk.Toplevel(self.root)
        add_window.title("Add Student")
        add_window.geometry("300x200")
        self.center_window(add_window)

        tk.Label(add_window, text="Student ID:").pack(pady=5)
        student_id_entry = tk.Entry(add_window)
        student_id_entry.pack(pady=5)

        tk.Label(add_window, text="Name:").pack(pady=5)
        name_entry = tk.Entry(add_window)
        name_entry.pack(pady=5)

        def capture_face():
            student_id = student_id_entry.get()
            name = name_entry.get()
            if not student_id or not name:
                messagebox.showerror("Error", "Please fill all fields")
                return

            video_capture = cv2.VideoCapture(0)
            if not video_capture.isOpened():
                messagebox.showerror("Error", "Could not open video device")
                return

            encodings = []
            for _ in range(5):  # Capture 5 samples
                ret, frame = video_capture.read()
                if not ret or frame is None:
                    continue
                # Ensure frame is in uint8 format
                if frame.dtype != np.uint8:
                    frame = frame.astype(np.uint8)
                try:
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                except Exception as conv_err:
                    logging.error(f"Color conversion error: {conv_err}")
                    continue

                face_locations = face_recognition.face_locations(rgb_frame)
                if face_locations:
                    face_encoding = face_recognition.face_encodings(rgb_frame, face_locations)[0]
                    encodings.append(face_encoding)
                time.sleep(0.5)

            video_capture.release()

            if not encodings:
                messagebox.showerror("Error", "No face detected")
                return

            # Average encodings
            avg_encoding = np.mean(encodings, axis=0)
            encoding_path = os.path.join(FACE_ENCODINGS_DIR, f"{student_id}.npy")
            np.save(encoding_path, avg_encoding)

            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("INSERT INTO students VALUES (?, ?, ?)",
                          (student_id, name, encoding_path))
                conn.commit()
                conn.close()
                self.load_encodings_cache()
                messagebox.showinfo("Success", "Student added successfully")
                add_window.destroy()
            except sqlite3.IntegrityError:
                messagebox.showerror("Error", "Student ID already exists")

        tk.Button(add_window, text="Capture Face", command=capture_face).pack(pady=10)

    def generate_report_ui(self):
        lecture_num = simpledialog.askinteger("Input", "Enter Lecture Number:",
                                             parent=self.root, minvalue=1, maxvalue=100)
        if lecture_num is None:
            return

        date = simpledialog.askstring("Input", "Enter Date (YYYY-MM-DD):", parent=self.root)
        if not date:
            return

        self.generate_attendance_report(date, lecture_num)
        messagebox.showinfo("Success", f"Report generated in {REPORTS_DIR}")

    def generate_attendance_report(self, date, lecture_num):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''SELECT students.student_id, students.name, attendance.timestamp 
                         FROM attendance JOIN students 
                         ON attendance.student_id = students.student_id
                         WHERE date=? AND lecture_number=? 
                         ORDER BY timestamp''', (date, lecture_num))
            records = c.fetchall()
            conn.close()

            if not records:
                messagebox.showinfo("Info", "No attendance records found")
                return

            filename = os.path.join(REPORTS_DIR, f"attendance_{date}_lecture{lecture_num}.pdf")
            doc = SimpleDocTemplate(filename, pagesize=letter)
            elements = []
            styles = getSampleStyleSheet()
            
            elements.append(Paragraph(f"Attendance Report - Lecture {lecture_num}", styles['Title']))
            elements.append(Paragraph(f"Date: {date}<br/>Total Students: {len(records)}", styles['Normal']))

            table_data = [["Student ID", "Name", "Time"]]
            for record in records:
                table_data.append(list(record))

            table = Table(table_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(table)
            doc.build(elements)
        except Exception as e:
            messagebox.showerror("Error", f"Report generation failed: {str(e)}")

    def scan_face(self):
        if not self.known_encodings:
            messagebox.showerror("Error", "No student faces registered in the system")
            return

        self.scan_window = tk.Toplevel(self.root)
        self.scan_window.title("Face Scanner")
        self.scan_window.geometry("800x600")
        self.center_window(self.scan_window)

        self.video_label = tk.Label(self.scan_window)
        self.video_label.pack()

        self.status_label = tk.Label(self.scan_window, text="Looking for face...", font=('Arial', 14))
        self.status_label.pack(pady=10)

        self.video_capture = cv2.VideoCapture(0)
        if not self.video_capture.isOpened():
            messagebox.showerror("Error", "Could not open video device")
            self.scan_window.destroy()
            return

        self.capture_active = True
        self.update_scan()

    def update_scan(self):
        if self.capture_active and self.video_capture.isOpened():
            ret, frame = self.video_capture.read()
            if not ret or frame is None:
                self.video_label.after(10, self.update_scan)
                return
            if frame.dtype != np.uint8:
                frame = frame.astype(np.uint8)
            try:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            except Exception as conv_err:
                logging.error(f"Color conversion error: {conv_err}")
                self.video_label.after(10, self.update_scan)
                return

            # Resize frame for faster processing
            small_frame = cv2.resize(rgb_frame, (0, 0), fx=0.25, fy=0.25)

            # Find all face locations and encodings
            face_locations = face_recognition.face_locations(small_frame)
            face_encodings = face_recognition.face_encodings(small_frame, face_locations)

            for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                # Scale back up face locations
                top *= 4
                right *= 4
                bottom *= 4
                left *= 4

                # Draw rectangle around face
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)

                # Compare with known faces
                matches = face_recognition.compare_faces(self.known_encodings, face_encoding)
                name = "Unknown"

                if True in matches:
                    first_match_index = matches.index(True)
                    student_id = self.known_student_ids[first_match_index]
                    name = self.get_student_name(student_id)
                    self.status_label.config(text=f"Recognized: {name} ({student_id})", fg="green")
                    self.mark_attendance(student_id)
                    self.capture_active = False
                    self.video_capture.release()
                    self.scan_window.after(2000, self.scan_window.destroy)
                    return

            # Display the resulting image; explicitly specify mode for Pillow
            try:
                img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), mode="RGB")
            except Exception as img_err:
                logging.error(f"Pillow conversion error: {img_err}")
                self.video_label.after(10, self.update_scan)
                return
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk
            self.video_label.config(image=imgtk)

            self.video_label.after(10, self.update_scan)

    def get_student_name(self, student_id):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT name FROM students WHERE student_id=?", (student_id,))
            result = c.fetchone()
            conn.close()
            return result[0] if result else "Unknown"
        except Exception as e:
            logging.error(f"Error getting student name: {str(e)}")
            return "Unknown"

    def mark_attendance(self, student_id):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Get the next lecture number (increment from last)
            c.execute("SELECT MAX(lecture_number) FROM attendance WHERE date=?", (today,))
            last_lecture = c.fetchone()[0]
            lecture_num = 1 if last_lecture is None else last_lecture + 1

            c.execute("INSERT INTO attendance (student_id, date, lecture_number, timestamp) VALUES (?, ?, ?, ?)",
                      (student_id, today, lecture_num, current_time))
            conn.commit()
            conn.close()
            logging.info(f"Attendance marked for {student_id}")
        except Exception as e:
            logging.error(f"Error marking attendance: {str(e)}")

if __name__ == "__main__":
    AttendanceSystem()
