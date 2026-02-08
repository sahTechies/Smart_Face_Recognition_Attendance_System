import os
import io
import threading
import sqlite3
import datetime
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, jsonify, send_file, abort
from model import train_model_background, extract_embedding_for_image, MODEL_PATH
from attendance_utils import mark_attendance

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "attendance.db")
DATASET_DIR = os.path.join(APP_DIR, "dataset")
os.makedirs(DATASET_DIR, exist_ok=True)

TRAIN_STATUS_FILE = os.path.join(APP_DIR, "train_status.json")

app = Flask(__name__, static_folder="static", template_folder="templates")

# ---------- DB helpers ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT,
                    roll TEXT,
                    class TEXT,
                    section TEXT,
                    reg_no TEXT,
                    created_at TEXT
                )""")
    c.execute("""CREATE TABLE IF NOT EXISTS attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER,
                    name TEXT,
                    timestamp TEXT
                )""")
    
    # Add email column if it doesn't exist (for existing databases)
    c.execute("PRAGMA table_info(students)")
    columns = [column[1] for column in c.fetchall()]
    if 'email' not in columns:
        c.execute("ALTER TABLE students ADD COLUMN email TEXT")
        print("Added email column to students table")
    
    conn.commit()
    conn.close()

init_db()

# ---------- Train status helpers ----------
def write_train_status(status_dict):
    with open(TRAIN_STATUS_FILE, "w") as f:
        json.dump(status_dict, f)

def read_train_status():
    if not os.path.exists(TRAIN_STATUS_FILE):
        return {"running": False, "progress": 0, "message": "Not trained"}
    with open(TRAIN_STATUS_FILE, "r") as f:
        return json.load(f)

# ensure initial train status file exists
write_train_status({"running": False, "progress": 0, "message": "No training yet."})

# ---------- Bulk Email Notification System ----------
@app.route("/send_emails", methods=["POST"])
def send_bulk_emails():
    try:
        data = request.get_json()
        target_date = data.get("date")
        
        if not target_date:
            return jsonify({"success": False, "message": "Date is required"}), 400
        
        # Validate date format
        try:
            datetime.datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            return jsonify({"success": False, "message": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        # Email credentials
        HOST_EMAIL = "h40313459@gmail.com"
        HOST_PASSWORD = "ivbw bape rokz bxbq"
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Fetch all students
        c.execute("SELECT id, name, email FROM students WHERE email IS NOT NULL AND email != ''")
        students = c.fetchall()
        
        if not students:
            return jsonify({"success": False, "message": "No students with email addresses found"}), 400
        
        emails_sent = 0
        emails_failed = 0
        
        # Connect to Gmail SMTP
        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(HOST_EMAIL, HOST_PASSWORD)
            
            for student_id, student_name, student_email in students:
                try:
                    # Check attendance for this student on the selected date
                    c.execute("SELECT timestamp FROM attendance WHERE student_id = ? AND date(timestamp) = ?", 
                              (student_id, target_date))
                    attendance_record = c.fetchone()
                    
                    if attendance_record:
                        # Student was present
                        subject = f"Attendance Alert: PRESENT - {student_name} - {target_date}"
                        body = f"""Dear Parent/Student,

This is to inform you that {student_name} was marked PRESENT on {target_date}.

Attendance Details:
• Student Name: {student_name}
• Date: {target_date}
• Status: PRESENT
• Marked At: {attendance_record[0]}

Thank you for your attention to this matter.

Best regards,
Digital Attendance System"""
                        
                        status = "PRESENT"
                    else:
                        # Student was absent
                        subject = f"Attendance Alert: ABSENT - {student_name} - {target_date}"
                        body = f"""Dear Parent/Student,

This is to inform you that {student_name} was marked ABSENT on {target_date}.

Attendance Details:
• Student Name: {student_name}
• Date: {target_date}
• Status: ABSENT
• Note: No attendance record found for this date

Please contact the school administration if you believe this is an error.

Best regards,
Digital Attendance System"""
                        
                        status = "ABSENT"
                    
                    # Create and send email
                    msg = MIMEMultipart()
                    msg['From'] = HOST_EMAIL
                    msg['To'] = student_email
                    msg['Subject'] = subject
                    
                    msg.attach(MIMEText(body, 'plain'))
                    
                    server.send_message(msg)
                    emails_sent += 1
                    
                    print(f"Email sent to {student_name} ({student_email}) - Status: {status}")
                    
                except Exception as e:
                    emails_failed += 1
                    print(f"Failed to send email to {student_name} ({student_email}): {str(e)}")
                    continue
            
            server.quit()
            
        except Exception as e:
            return jsonify({"success": False, "message": f"Email server error: {str(e)}"}), 500
        
        finally:
            conn.close()
        
        # Return results
        message = f"Email notification completed! ✅\n\n"
        message += f"📧 Emails Sent: {emails_sent}\n"
        if emails_failed > 0:
            message += f"❌ Emails Failed: {emails_failed}\n"
        message += f"📅 Date: {target_date}"
        
        return jsonify({
            "success": True, 
            "message": message,
            "emails_sent": emails_sent,
            "emails_failed": emails_failed,
            "total_students": len(students)
        })
        
    except Exception as e:
        print(f"Bulk email error: {str(e)}")
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

# ---------- Routes ----------
@app.route("/")
def index():
    return render_template("index.html")

# Dashboard simple API for attendance stats (last 30 days)
@app.route("/attendance_stats")
def attendance_stats():
    import pandas as pd
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT timestamp FROM attendance", conn)
    conn.close()
    if df.empty:
        from datetime import date, timedelta
        days = [(date.today() - datetime.timedelta(days=i)).strftime("%d-%b") for i in range(29, -1, -1)]
        return jsonify({"dates": days, "counts": [0]*30})
    df['date'] = pd.to_datetime(df['timestamp']).dt.date
    last_30 = [ (datetime.date.today() - datetime.timedelta(days=i)) for i in range(29, -1, -1) ]
    counts = [ int(df[df['date'] == d].shape[0]) for d in last_30 ]
    dates = [ d.strftime("%d-%b") for d in last_30 ]
    return jsonify({"dates": dates, "counts": counts})

# -------- Add student (form) --------
@app.route("/add_student", methods=["GET", "POST"])
def add_student():
    if request.method == "GET":
        return render_template("add_student.html")
# POST: save student metadata and return student_id
    data = request.form
    name = data.get("name","").strip()
    email = data.get("email","").strip()
    roll = data.get("roll","").strip()
    cls = data.get("class","").strip()
    sec = data.get("sec","").strip()
    reg_no = data.get("reg_no","").strip()
    if not name:
        return jsonify({"error":"name required"}), 400
    if not email:
        return jsonify({"error":"email required"}), 400
    
    # Basic email validation
    import re
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return jsonify({"error":"invalid email format"}), 400
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    c.execute("INSERT INTO students (name, email, roll, class, section, reg_no, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (name, email, roll, cls, sec, reg_no, now))
    sid = c.lastrowid
    conn.commit()
    conn.close()
    # create dataset folder for this student
    os.makedirs(os.path.join(DATASET_DIR, str(sid)), exist_ok=True)
    return jsonify({"student_id": sid})

# -------- Upload face images (after capture) --------
@app.route("/upload_face", methods=["POST"])
def upload_face():
    student_id = request.form.get("student_id")
    if not student_id:
        return jsonify({"error":"student_id required"}), 400
    files = request.files.getlist("images[]")
    saved = 0
    folder = os.path.join(DATASET_DIR, student_id)
    if not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
    for f in files:
        try:
            fname = f"{datetime.datetime.utcnow().timestamp():.6f}_{saved}.jpg"
            path = os.path.join(folder, fname)
            f.save(path)
            saved += 1
        except Exception as e:
            app.logger.error("save error: %s", e)
    return jsonify({"saved": saved})

# -------- Train model (start background thread) --------
@app.route("/train_model", methods=["GET"])
def train_model_route():
    # if already running, respond accordingly
    status = read_train_status()
    if status.get("running"):
        return jsonify({"status":"already_running"}), 202
    # reset status
    write_train_status({"running": True, "progress": 0, "message": "Starting training"})
    # start background thread with proper status reset on completion
    def progress_callback(p, m):
        is_complete = (p >= 100) or ("error" in m.lower()) or ("not found" in m.lower()) or ("no training" in m.lower())
        write_train_status({"running": not is_complete, "progress": p, "message": m})
    
    t = threading.Thread(target=train_model_background, args=(DATASET_DIR, progress_callback))
    t.daemon = True
    t.start()
    return jsonify({"status":"started"}), 202

# -------- Train progress (polling) --------
@app.route("/train_status", methods=["GET"])
def train_status():
    return jsonify(read_train_status())

# -------- Mark attendance page --------
@app.route("/mark_attendance", methods=["GET"])
def mark_attendance_page():
    return render_template("mark_attendance.html")

# -------- Recognize face endpoint (POST image) --------
@app.route("/recognize_face", methods=["POST"])
def recognize_face():
    if "image" not in request.files:
        return jsonify({"recognized": False, "error":"no image"}), 400
    img_file = request.files["image"]
    attendance_date = request.form.get("attendance_date", "").strip()
    
    # Validate attendance_date format if provided
    if attendance_date:
        try:
            # Validate date format
            datetime.datetime.strptime(attendance_date, "%Y-%m-%d")
        except ValueError:
            return jsonify({"recognized": False, "error":"invalid date format. Use YYYY-MM-DD"}), 400
    
    try:
        emb = extract_embedding_for_image(img_file.stream)
        if emb is None:
            return jsonify({"recognized": False, "error":"no face detected"}), 200
        # attempt prediction
        from model import load_model_if_exists, predict_with_model
        clf = load_model_if_exists()
        if clf is None:
            return jsonify({"recognized": False, "error":"model not trained"}), 200
        pred_label, conf = predict_with_model(clf, emb)
        # threshold confidence
        if conf < 0.5:
            return jsonify({"recognized": False, "confidence": float(conf)}), 200
        # find student name
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT name FROM students WHERE id=?", (int(pred_label),))
        row = c.fetchone()
        name = row[0] if row else "Unknown"
        conn.close()
        
        # mark attendance for specified date (prevents duplicates for that date)
        attendance_marked = mark_attendance(int(pred_label), name, attendance_date if attendance_date else None)
        date_label = attendance_date if attendance_date and attendance_date != datetime.date.today().isoformat() else "today"
        if attendance_marked:
            print(f"Attendance marked for {name} (ID: {pred_label}) for {date_label}")
        else:
            print(f"Attendance already exists for {name} (ID: {pred_label}) for {date_label}")
        return jsonify({"recognized": True, "student_id": int(pred_label), "name": name, "confidence": float(conf)}), 200
    except Exception as e:
        app.logger.exception("recognize error")
        return jsonify({"recognized": False, "error": str(e)}), 500

# -------- Attendance records & filters --------
@app.route("/attendance_record", methods=["GET"])
def attendance_record():
    period = request.args.get("period", "all")  # all, daily, weekly, monthly
    view_type = request.args.get("view", "present")  # present, absent
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if view_type == "absent":
        # Show absent students (registered but not present in attendance)
        q = "SELECT id, name, email, roll, class, section, reg_no, created_at FROM students ORDER BY id"
        params = ()
        
        if period == "daily":
            target_date = datetime.date.today().isoformat()
        elif period == "weekly":
            target_date = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        elif period == "monthly":
            target_date = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
        else:
            target_date = datetime.date.today().isoformat()
        
        c.execute(q, params)
        all_students = c.fetchall()
        
        # Get present students for the period
        if period == "daily":
            c.execute("SELECT DISTINCT student_id FROM attendance WHERE date(timestamp) = ?", (target_date,))
        elif period == "weekly":
            c.execute("SELECT DISTINCT student_id FROM attendance WHERE date(timestamp) >= ?", (target_date,))
        elif period == "monthly":
            c.execute("SELECT DISTINCT student_id FROM attendance WHERE date(timestamp) >= ?", (target_date,))
        else:
            c.execute("SELECT DISTINCT student_id FROM attendance WHERE date(timestamp) = ?", (target_date,))
        
        present_ids = set(row[0] for row in c.fetchall())
        
        # Filter students who were absent
        absent_records = []
        for student in all_students:
            if student[0] not in present_ids:  # Student ID not in present list
                absent_records.append(student)
        
        conn.close()
        return render_template("attendance_record.html", records=absent_records, period=period, view_type=view_type)
    
    else:
        # Show present students (original functionality)
        q = "SELECT id, student_id, name, timestamp FROM attendance"
        params = ()
        if period == "daily":
            today = datetime.date.today().isoformat()
            q += " WHERE date(timestamp) = ?"
            params = (today,)
        elif period == "weekly":
            start = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
            q += " WHERE date(timestamp) >= ?"
            params = (start,)
        elif period == "monthly":
            start = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
            q += " WHERE date(timestamp) >= ?"
            params = (start,)
        q += " ORDER BY timestamp DESC LIMIT 5000"
        c.execute(q, params)
        rows = c.fetchall()
        conn.close()
        return render_template("attendance_record.html", records=rows, period=period, view_type=view_type)

# -------- CSV download --------
@app.route("/download_csv", methods=["GET"])
def download_csv():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT a.id, a.student_id, s.name, s.email, a.timestamp 
                 FROM attendance a 
                 LEFT JOIN students s ON a.student_id = s.id 
                 ORDER BY a.timestamp DESC""")
    rows = c.fetchall()
    conn.close()
    output = io.StringIO()
    output.write("id,student_id,name,email,timestamp\n")
    for r in rows:
        output.write(f'{r[0]},{r[1]},{r[2]},{r[3]},{r[4]}\n')
    mem = io.BytesIO()
    mem.write(output.getvalue().encode("utf-8"))
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name="attendance.csv", mimetype="text/csv")

# -------- Daily Attendance CSV with Absent Students --------
@app.route("/download_daily_attendance", methods=["GET"])
def download_daily_attendance():
    date_param = request.args.get("date", datetime.date.today().isoformat())
    
    try:
        # Validate date format
        datetime.datetime.strptime(date_param, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Get all registered students
    c.execute("SELECT id, name, email, roll, class, section, reg_no FROM students ORDER BY id")
    all_students = c.fetchall()
    
    # Get students marked present for the specific date
    c.execute("""SELECT DISTINCT a.student_id, a.name, a.timestamp
                 FROM attendance a 
                 WHERE date(a.timestamp) = ?
                 ORDER BY a.student_id""", (date_param,))
    present_students = c.fetchall()
    
    # Create set of present student IDs for quick lookup
    present_ids = set(row[0] for row in present_students)
    present_details = {row[0]: {"name": row[1], "timestamp": row[2]} for row in present_students}
    
    conn.close()
    
    output = io.StringIO()
    output.write("Student_ID,Name,Email,Roll_No,Class,Section,Reg_No,Status,Attendance_Time\n")
    
    absent_count = 0
    present_count = 0
    
    for student in all_students:
        student_id, name, email, roll, class_name, section, reg_no = student
        
        if student_id in present_ids:
            # Student was marked present
            status = "Present"
            attendance_time = present_details[student_id]["timestamp"]
            present_count += 1
        else:
            # Student was not marked present - mark as absent
            status = "Absent"
            attendance_time = "Not marked"
            absent_count += 1
        
        # Properly escape CSV fields
        name_quoted = f'"{name}"' if name else '""'
        email_quoted = f'"{email}"' if email else '""'
        roll_quoted = f'"{roll}"' if roll else '""'
        class_quoted = f'"{class_name}"' if class_name else '""'
        section_quoted = f'"{section}"' if section else '""'
        reg_no_quoted = f'"{reg_no}"' if reg_no else '""'
        attendance_time_quoted = f'"{attendance_time}"'
        
        output.write(f'{student_id},{name_quoted},{email_quoted},{roll_quoted},{class_quoted},{section_quoted},{reg_no_quoted},{status},{attendance_time_quoted}\n')
    
    # Add summary at the end
    output.write(f"\n,,,,,,Summary,,\n")
    output.write(f",Total Students,{len(all_students)},,,,\n")
    output.write(f",Present Students,{present_count},,,,,\n")
    output.write(f",Absent Students,{absent_count},,,,,\n")
    output.write(f",Date,{date_param},,,,,\n")
    
    mem = io.BytesIO()
    mem.write(output.getvalue().encode("utf-8"))
    mem.seek(0)
    
    filename = f"daily_attendance_{date_param}.csv"
    return send_file(mem, as_attachment=True, download_name=filename, mimetype="text/csv")

# -------- Registered Students Page --------
@app.route("/registered_students", methods=["GET"])
def registered_students_page():
    return render_template("registered_students.html")

# -------- Present Students API for date-specific attendance --------
@app.route("/present_students", methods=["GET"])
def present_students():
    date_param = request.args.get("date", datetime.date.today().isoformat())
    
    try:
        # Validate date format
        datetime.datetime.strptime(date_param, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Get all registered students
    c.execute("SELECT id, name, email, roll, class, section, reg_no FROM students ORDER BY id")
    all_students = c.fetchall()
    
    # Get students marked present for the specific date
    c.execute("""SELECT a.student_id, a.name, a.timestamp
                 FROM attendance a 
                 WHERE date(a.timestamp) = ?
                 ORDER BY a.timestamp""", (date_param,))
    present_students = c.fetchall()
    
    # Create lookup for present students
    present_details = {row[0]: {"name": row[1], "timestamp": row[2]} for row in present_students}
    present_ids = set(present_details.keys())
    
    # Prepare results
    results = []
    present_count = 0
    absent_count = 0
    
    for student in all_students:
        student_id, name, email, roll, class_name, section, reg_no = student
        
        if student_id in present_ids:
            # Student is present
            results.append({
                "id": student_id,
                "name": name,
                "email": email,
                "roll": roll,
                "class": class_name,
                "section": section,
                "reg_no": reg_no,
                "status": "Present",
                "attendance_time": present_details[student_id]["timestamp"]
            })
            present_count += 1
        else:
            # Student is absent
            results.append({
                "id": student_id,
                "name": name,
                "email": email,
                "roll": roll,
                "class": class_name,
                "section": section,
                "reg_no": reg_no,
                "status": "Absent",
                "attendance_time": "Not marked"
            })
            absent_count += 1
    
    conn.close()
    
    return jsonify({
        "date": date_param,
        "present_count": present_count,
        "absent_count": absent_count,
        "total_students": len(all_students),
        "students": results
    })

# -------- Students API for listing/editing --------
@app.route("/students", methods=["GET"])
def students_list():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, email, roll, class, section, reg_no, created_at FROM students ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    data = [ {"id":r[0],"name":r[1],"email":r[2],"roll":r[3],"class":r[4],"section":r[5],"reg_no":r[6],"created_at":r[7]} for r in rows ]
    return jsonify({"students": data})

@app.route("/students/<int:sid>", methods=["DELETE"])
def delete_student(sid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM students WHERE id=?", (sid,))
    c.execute("DELETE FROM attendance WHERE student_id=?", (sid,))
    conn.commit()
    conn.close()
    # also delete dataset folder
    folder = os.path.join(DATASET_DIR, str(sid))
    if os.path.isdir(folder):
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
    return jsonify({"deleted": True})

# ---------------- run ------------------------
if __name__ == "__main__":
    app.run(debug=True)