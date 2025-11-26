import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import cv2
import face_recognition
import numpy as np
import os
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from PIL import Image, ImageTk
from config import DB_PATH, FACE_ENCODINGS_DIR, REPORTS_DIR, LOG_DIR
import logging

class AdminPanel:
    def __init__(self, parent, main_app):
        self.parent = parent
        self.main_app = main_app
        self.window = tk.Toplevel(parent)
        self.window.title("Admin Panel")
        self.window.geometry("1000x700")
        self.center_window(self.window)
        
        self.video_capture = None
        self.capture_active = False
        self.face_encoding = None
        self.temp_student_data = {}
        
        self.create_widgets()
        self.load_students()
        self.load_statistics()
        self.window.protocol("WM_DELETE_WINDOW", self.cleanup)

    def center_window(self, window):
        window.update_idletasks()
        width = window.winfo_width()
        height = window.winfo_height()
        x = (window.winfo_screenwidth() // 2) - (width // 2)
        y = (window.winfo_screenheight() // 2) - (height // 2)
        window.geometry(f'{width}x{height}+{x}+{y}')

    def cleanup(self):
        self.capture_active = False
        if self.video_capture and self.video_capture.isOpened():
            self.video_capture.release()
        self.window.destroy()

    def create_widgets(self):
        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Students Tab
        self.create_students_tab()
        # Reports Tab
        self.create_reports_tab()
        # Statistics Tab
        self.create_stats_tab()

    def create_students_tab(self):
        students_tab = ttk.Frame(self.notebook)
        self.notebook.add(students_tab, text="Students")

        # Treeview with scrollbar
        tree_frame = tk.Frame(students_tab)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree = ttk.Treeview(tree_frame, columns=('ID', 'Name'), show='headings',
                                yscrollcommand=scrollbar.set)
        self.tree.heading('ID', text='Student ID')
        self.tree.heading('Name', text='Name')
        self.tree.pack(fill=tk.BOTH, expand=True)

        scrollbar.config(command=self.tree.yview)

        # Control buttons
        btn_frame = tk.Frame(students_tab)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        btn_register = tk.Button(btn_frame, text="Register New Student",
                                command=self.show_registration_window)
        btn_register.pack(side=tk.LEFT, padx=5)

        btn_delete = tk.Button(btn_frame, text="Delete Student",
                              command=self.delete_student)
        btn_delete.pack(side=tk.LEFT, padx=5)

        btn_refresh = tk.Button(btn_frame, text="Refresh List",
                               command=self.load_students)
        btn_refresh.pack(side=tk.LEFT, padx=5)

    def show_registration_window(self):
        reg_window = tk.Toplevel(self.window)
        reg_window.title("New Student Registration")
        reg_window.geometry("400x300")
        self.center_window(reg_window)

        tk.Label(reg_window, text="Student Registration", font=('Arial', 14)).pack(pady=10)

        tk.Label(reg_window, text="Student ID:").pack()
        student_id_entry = tk.Entry(reg_window)
        student_id_entry.pack(pady=5)

        tk.Label(reg_window, text="Full Name:").pack()
        name_entry = tk.Entry(reg_window)
        name_entry.pack(pady=5)

        status_label = tk.Label(reg_window, text="", fg="red")
        status_label.pack(pady=5)

        def proceed_to_face_capture():
            student_id = student_id_entry.get().strip()
            name = name_entry.get().strip()

            if not student_id or not name:
                status_label.config(text="All fields are required", fg="red")
                return

            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("SELECT 1 FROM students WHERE student_id=?", (student_id,))
                if c.fetchone():
                    status_label.config(text=f"ID {student_id} already exists", fg="red")
                    return
            finally:
                conn.close()

            reg_window.destroy()
            self.temp_student_data = {'id': student_id, 'name': name}
            self.show_face_capture_interface()

        tk.Button(reg_window, text="Next → Face Capture",
                 command=proceed_to_face_capture).pack(pady=10)

    def show_face_capture_interface(self):
        self.capture_window = tk.Toplevel(self.window)
        self.capture_window.title("Face Capture")
        self.capture_window.geometry("800x600")
        self.center_window(self.capture_window)

        # Video preview
        self.video_label = tk.Label(self.capture_window)
        self.video_label.pack(pady=10)

        # Status messages
        self.capture_status = tk.Label(self.capture_window, text="", fg="red")
        self.capture_status.pack()

        # Control buttons
        btn_frame = tk.Frame(self.capture_window)
        btn_frame.pack(pady=10)

        self.capture_btn = tk.Button(btn_frame, text="Capture Face",
                                   command=self.capture_face)
        self.capture_btn.pack(side=tk.LEFT, padx=10)

        self.save_btn = tk.Button(btn_frame, text="Save Student", state=tk.DISABLED,
                                command=self.save_student)
        self.save_btn.pack(side=tk.LEFT, padx=10)

        # Initialize video capture
        self.video_capture = cv2.VideoCapture(0)
        if not self.video_capture.isOpened():
            self.capture_status.config(text="Error accessing camera", fg="red")
            return

        self.video_capture.set(3, 640)  # Width
        self.video_capture.set(4, 480)  # Height
        self.capture_active = True
        self.update_preview()

    def update_preview(self):
        if self.capture_active and self.video_capture.isOpened():
            ret, frame = self.video_capture.read()
            if ret:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                face_locations = face_recognition.face_locations(rgb_frame)
                
                for (top, right, bottom, left) in face_locations:
                    cv2.rectangle(rgb_frame, (left, top), (right, bottom), (0, 255, 0), 2)
                
                img = Image.fromarray(rgb_frame)
                imgtk = ImageTk.PhotoImage(image=img)
                self.video_label.imgtk = imgtk
                self.video_label.config(image=imgtk)
            
            self.video_label.after(10, self.update_preview)

    def capture_face(self):
        if not self.video_capture.isOpened():
            self.capture_status.config(text="Camera not available", fg="red")
            return

        ret, frame = self.video_capture.read()
        if not ret:
            self.capture_status.config(text="Error capturing frame", fg="red")
            return

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        try:
            face_locations = face_recognition.face_locations(
                rgb_frame, model="hog", number_of_times_to_upsample=2
            )
            
            if len(face_locations) != 1:
                error_msg = "No face detected" if len(face_locations) == 0 else "Multiple faces detected"
                raise ValueError(error_msg)
            
            face_encodings = face_recognition.face_encodings(
                rgb_frame, face_locations, num_jitters=3, model="large"
            )
            
            if not face_encodings:
                raise ValueError("Failed to generate face encoding")
            
            self.face_encoding = face_encodings[0]
            self.capture_status.config(text="Face captured successfully!", fg="green")
            self.save_btn.config(state=tk.NORMAL)
            
        except Exception as e:
            self.capture_status.config(text=f"Error: {str(e)}", fg="red")

    def save_student(self):
        try:
            os.makedirs(FACE_ENCODINGS_DIR, exist_ok=True)
            encoding_path = os.path.join(FACE_ENCODINGS_DIR, f"{self.temp_student_data['id']}.npy")
            np.save(encoding_path, self.face_encoding)

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(
                "INSERT INTO students (name, student_id, face_encoding_path) VALUES (?, ?, ?)",
                (self.temp_student_data['name'], self.temp_student_data['id'], encoding_path)
            )
            conn.commit()
            messagebox.showinfo("Success", "Student registered successfully!")
            logging.info(f"New student registered: {self.temp_student_data['id']}")
            self.load_students()
            self.main_app.load_encodings_cache()
            self.capture_window.destroy()

        except Exception as e:
            error_msg = f"Registration failed: {str(e)}"
            messagebox.showerror("Error", error_msg)
            logging.error(error_msg)
        finally:
            if 'conn' in locals():
                conn.close()
            self.cleanup_camera()

    def cleanup_camera(self):
        self.capture_active = False
        if self.video_capture and self.video_capture.isOpened():
            self.video_capture.release()
        self.face_encoding = None

    def load_students(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            self.tree.delete(*self.tree.get_children())
            c.execute("SELECT student_id, name FROM students ORDER BY student_id")
            for row in c.fetchall():
                self.tree.insert('', 'end', values=row)
            
            conn.close()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load students: {str(e)}")
            logging.error(f"Error loading students: {str(e)}")

    def delete_student(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a student to delete")
            return
        
        student_id = self.tree.item(selected[0])['values'][0]
        
        if messagebox.askyesno("Confirm", f"Delete student {student_id}? This will also remove attendance records."):
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                
                # Get encoding path
                c.execute("SELECT face_encoding_path FROM students WHERE student_id=?", (student_id,))
                result = c.fetchone()
                if result and os.path.exists(result[0]):
                    os.remove(result[0])
                
                # Delete records
                c.execute("DELETE FROM students WHERE student_id=?", (student_id,))
                c.execute("DELETE FROM attendance WHERE student_id=?", (student_id,))
                conn.commit()
                
                self.load_students()
                self.main_app.load_encodings_cache()
                message = f"Student {student_id} deleted successfully"
                messagebox.showinfo("Success", message)
                logging.info(message)
                
            except Exception as e:
                error_msg = f"Deletion failed: {str(e)}"
                messagebox.showerror("Error", error_msg)
                logging.error(error_msg)
            finally:
                conn.close()

    def create_reports_tab(self):
        reports_tab = ttk.Frame(self.notebook)
        self.notebook.add(reports_tab, text="Reports")

        # Date selection
        date_frame = tk.Frame(reports_tab)
        date_frame.pack(pady=10)
        tk.Label(date_frame, text="Date (YYYY-MM-DD):").pack(side=tk.LEFT)
        self.report_date = tk.Entry(date_frame)
        self.report_date.pack(side=tk.LEFT, padx=5)
        self.report_date.insert(0, datetime.now().strftime("%Y-%m-%d"))

        # Lecture number
        lecture_frame = tk.Frame(reports_tab)
        lecture_frame.pack(pady=5)
        tk.Label(lecture_frame, text="Lecture Number:").pack(side=tk.LEFT)
        self.report_lecture = tk.Entry(lecture_frame)
        self.report_lecture.pack(side=tk.LEFT, padx=5)

        # Generate button
        tk.Button(reports_tab, text="Generate PDF Report",
                command=self.generate_report).pack(pady=10)

    def generate_report(self):
        date = self.report_date.get()
        lecture_num = self.report_lecture.get()

        if not date or not lecture_num:
            messagebox.showerror("Error", "Please fill all fields")
            return

        try:
            lecture_num = int(lecture_num)
        except ValueError:
            messagebox.showerror("Error", "Invalid lecture number")
            return

        try:
            os.makedirs(REPORTS_DIR, exist_ok=True)
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
            self.create_pdf_report(filename, records, date, lecture_num)
            messagebox.showinfo("Success", f"Report generated:\n{filename}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate report: {str(e)}")

    def create_pdf_report(self, filename, records, date, lecture_num):
        try:
            from reportlab.lib.pagesizes import letter
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
            raise Exception(f"PDF creation error: {str(e)}")

    def create_stats_tab(self):
        stats_tab = ttk.Frame(self.notebook)
        self.notebook.add(stats_tab, text="Statistics")

        # Stats display
        self.stats_text = tk.Text(stats_tab, height=20, width=80)
        self.stats_text.pack(pady=10)

        # Refresh button
        tk.Button(stats_tab, text="Refresh Statistics",
                 command=self.load_statistics).pack(pady=5)

    def load_statistics(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            stats = {
                'total_students': c.execute("SELECT COUNT(*) FROM students").fetchone()[0],
                'today_attendance': c.execute("SELECT COUNT(DISTINCT student_id) FROM attendance WHERE date=?", 
                                            (datetime.now().date(),)).fetchone()[0],
                'recent_lectures': c.execute('''SELECT date, lecture_number, COUNT(DISTINCT student_id) 
                                              FROM attendance GROUP BY date, lecture_number 
                                              ORDER BY date DESC LIMIT 5''').fetchall(),
                'top_attendees': c.execute('''SELECT students.student_id, students.name, COUNT(*) 
                                            FROM attendance JOIN students 
                                            ON attendance.student_id = students.student_id 
                                            GROUP BY students.student_id 
                                            ORDER BY COUNT(*) DESC LIMIT 5''').fetchall()
            }
            conn.close()

            # Format statistics
            stats_text = f"Total Students: {stats['total_students']}\n"
            stats_text += f"Today's Attendance: {stats['today_attendance']}\n\n"
            stats_text += "Recent Lectures:\n"
            for date, lecture, count in stats['recent_lectures']:
                stats_text += f"{date} - Lecture {lecture}: {count} students\n"
            stats_text += "\nTop Attendees:\n"
            for sid, name, count in stats['top_attendees']:
                stats_text += f"{name} ({sid}): {count} attendances\n"

            self.stats_text.delete(1.0, tk.END)
            self.stats_text.insert(tk.END, stats_text)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load statistics: {str(e)}")
            logging.error(f"Statistics error: {str(e)}")