import tkinter as tk
from tkinter import messagebox, simpledialog
import cv2
import face_recognition
import numpy as np
from PIL import Image, ImageTk
import os
import sqlite3
from datetime import datetime
from config import DB_PATH, FACE_ENCODINGS_DIR, REPORTS_DIR, LOG_DIR
from database import init_db
from admin_panel import AdminPanel
from config import DB_PATH, FACE_ENCODINGS_DIR, REPORTS_DIR, LOG_DIR
import threading
import time
import logging
import hashlib

# Set up logging
logging.basicConfig(
    filename=os.path.join(LOG_DIR, 'attendance.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

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
        
        btn_admin = tk.Button(main_frame, text="Admin Login", command=self.open_admin_login, 
                             width=20, height=2)
        btn_admin.pack(pady=10)
        
        btn_scan = tk.Button(main_frame, text="Mark Attendance", command=self.scan_face, 
                            width=20, height=2)
        btn_scan.pack(pady=10)
    
    def open_admin_login(self):
        login_window = tk.Toplevel(self.root)
        login_window.title("Admin Login")
        login_window.geometry("300x200")
        self.center_window(login_window)
        
        tk.Label(login_window, text="Username:").pack(pady=5)
        self.username_entry = tk.Entry(login_window)
        self.username_entry.pack(pady=5)
        
        tk.Label(login_window, text="Password:").pack(pady=5)
        self.password_entry = tk.Entry(login_window, show="*")
        self.password_entry.pack(pady=5)
        
        btn_login = tk.Button(login_window, text="Login", 
                            command=lambda: self.verify_admin(login_window))
        btn_login.pack(pady=10)
    
    def verify_admin(self, window):
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
                window.destroy()
                AdminPanel(self.root, self)
                logging.info(f"Admin {username} logged in successfully")
            else:
                messagebox.showerror("Error", "Invalid credentials")
                logging.warning(f"Failed login attempt for username: {username}")
        except Exception as e:
            messagebox.showerror("Error", f"Login failed: {str(e)}")
            logging.error(f"Admin login error: {str(e)}")
    
    def scan_face(self):
        if not self.known_encodings:
            messagebox.showerror("Error", "No students registered in the system")
            return

        # First get lecture number
        lecture_num = simpledialog.askinteger("Input", "Enter Lecture Number:", 
                                            parent=self.root,
                                            minvalue=1, maxvalue=100)
        if lecture_num is None:  # User cancelled
            return

        # Now create the video window
        self.video_capture = cv2.VideoCapture(0)
        if not self.video_capture.isOpened():
            messagebox.showerror("Error", "Could not open video device")
            return

        # Set video capture size
        self.video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        # Create the video window
        self.video_window = tk.Toplevel(self.root)
        self.video_window.title(f"Marking Attendance - Lecture {lecture_num}")
        self.video_window.geometry("1000x800")
        
        # Force window to stay on top
        self.video_window.attributes('-topmost', True)
        
        # Center the window
        self.center_window(self.video_window)
        
        # Bring to front and focus
        self.video_window.lift()
        self.video_window.focus_force()

        self.video_label = tk.Label(self.video_window)
        self.video_label.pack(expand=True, fill=tk.BOTH)

        self.capture_active = True
        self.last_processed = time.time()
        self.processed_students = set()
        self.marked_students = set()

        def update_frame():
                if not self.capture_active:
                    return

                ret, frame = self.video_capture.read()
                if not ret:
                    return

                # Process at 3 FPS
                process_frame = (time.time() - self.last_processed) > 0.33

                # Get original frame dimensions
                orig_height, orig_width = frame.shape[:2]
                
                # Create display frame (resized for the window)
                display_ratio = 900 / orig_width  # We'll display at 900px width
                display_frame = cv2.resize(frame, (900, int(orig_height * display_ratio)))

                if process_frame:
                    # Create smaller frame for processing (half size)
                    small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
                    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

                    face_locations = face_recognition.face_locations(rgb_small_frame)
                    face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

                    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                        # Scale face locations back to original frame size (not display size)
                        # Since we processed at 0.5x scale, multiply by 2
                        top *= 2
                        right *= 2
                        bottom *= 2
                        left *= 2

                        # Now scale to display size
                        display_top = int(top * display_ratio)
                        display_right = int(right * display_ratio)
                        display_bottom = int(bottom * display_ratio)
                        display_left = int(left * display_ratio)

                        matches = face_recognition.compare_faces(
                            self.known_encodings,
                            face_encoding,
                            tolerance=0.5
                        )
                        face_distances = face_recognition.face_distance(self.known_encodings, face_encoding)
                        best_match_index = np.argmin(face_distances)

                        if matches[best_match_index] and face_distances[best_match_index] < 0.6:
                            student_id = self.known_student_ids[best_match_index]
                            
                            if student_id not in self.marked_students:
                                self.marked_students.add(student_id)
                                self.root.after(0, lambda: self.mark_attendance(student_id, lecture_num))

                        # Draw on display frame using display-scaled coordinates
                        color = (0, 255, 0) if (matches[best_match_index] and face_distances[best_match_index] < 0.6) else (0, 0, 255)
                        cv2.rectangle(display_frame, 
                                    (display_left, display_top), 
                                    (display_right, display_bottom), 
                                    color, 2)
                        label = student_id if (matches[best_match_index] and face_distances[best_match_index] < 0.6) else "Unknown"
                        cv2.putText(display_frame, label, 
                                (display_left + 6, display_bottom - 6), 
                                cv2.FONT_HERSHEY_DUPLEX, 0.8, color, 1)

                    self.last_processed = time.time()

                # Convert for display
                img = Image.fromarray(cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB))
                imgtk = ImageTk.PhotoImage(image=img)
                self.video_label.imgtk = imgtk
                self.video_label.configure(image=imgtk)

                if self.capture_active:
                    self.video_label.after(10, update_frame)

        def on_closing():
            self.capture_active = False
            if self.video_capture.isOpened():
                self.video_capture.release()
            self.video_window.destroy()

        self.video_window.protocol("WM_DELETE_WINDOW", on_closing)
        update_frame()

    def mark_attendance(self, student_id, lecture_num):
        try:
            current_date = datetime.now().strftime("%Y-%m-%d")
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()

            # Check for existing entry
            c.execute('''SELECT 1 FROM attendance 
                        WHERE student_id=? AND date=? AND lecture_number=?''',
                    (student_id, current_date, lecture_num))
            exists = c.fetchone()

            if not exists:
                c.execute('''INSERT INTO attendance 
                            (student_id, date, lecture_number, timestamp)
                            VALUES (?, ?, ?, ?)''',
                        (student_id, current_date, lecture_num, current_time))
                conn.commit()
                
                # Generate report after marking attendance
                self.generate_attendance_report(current_date, lecture_num)
                
                messagebox.showinfo("Success", f"Attendance marked for {student_id}")
            else:
                messagebox.showinfo("Info", f"Attendance already recorded for {student_id}")

        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Failed to mark attendance: {str(e)}")
        finally:
            if conn:
                conn.close()

    def generate_attendance_report(self, date, lecture_num):
        """Generate a PDF report for the attendance"""
        try:
            # Ensure reports directory exists
            os.makedirs(REPORTS_DIR, exist_ok=True)
            
            # Connect to database
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            # Get attendance data
            c.execute('''SELECT students.student_id, students.name, attendance.timestamp 
                    FROM attendance JOIN students 
                    ON attendance.student_id = students.student_id
                    WHERE date=? AND lecture_number=? 
                    ORDER BY timestamp''', (date, lecture_num))
            
            records = c.fetchall()
            
            if not records:
                return  # No records to report
            
            # Create PDF filename
            filename = os.path.join(REPORTS_DIR, f"attendance_{date}_lecture{lecture_num}.pdf")
            
            # Create PDF document
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
            from reportlab.lib import colors
            
            doc = SimpleDocTemplate(filename, pagesize=letter)
            elements = []
            styles = getSampleStyleSheet()
            
            # Title
            title = Paragraph(f"Attendance Report - Lecture {lecture_num}", styles['Title'])
            elements.append(title)
            
            # Report details
            details = Paragraph(f"Date: {date}<br/>Total Students: {len(records)}", styles['Normal'])
            elements.append(details)
            
            # Create table data
            table_data = [["Student ID", "Name", "Time"]]  # Headers
            
            for record in records:
                table_data.append(list(record))
            
            # Create table
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
            print(f"Error generating report: {e}")
if __name__ == "__main__":
    AttendanceSystem()