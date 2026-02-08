import sqlite3
import datetime
import os
import threading

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "attendance.db")

# Global lock to prevent race conditions
attendance_lock = threading.Lock()

def init_unique_constraint():
    """Add unique constraint to prevent duplicate attendance entries for same student on same day"""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # First drop the index if it exists to recreate properly
        c.execute("DROP INDEX IF EXISTS idx_student_daily_attendance")
        conn.commit()
        # Create unique index on student_id and date part of timestamp
        c.execute("""CREATE UNIQUE INDEX idx_student_daily_attendance 
                     ON attendance (student_id, date(timestamp))""")
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error creating constraint: {e}")
    finally:
        if conn:
            conn.close()

# Initialize the constraint when module is imported
init_unique_constraint()

def mark_attendance(student_id, name, attendance_date=None):
    """
    Mark attendance for a student, preventing duplicate entries for the same day.
    
    Args:
        student_id (int): The ID of the student
        name (str): The name of the student
        attendance_date (str, optional): Date in YYYY-MM-DD format. Defaults to today.
    
    Returns:
        bool: True if attendance was marked, False if already exists or error
    """
    with attendance_lock:
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            # Use provided date or today's date in YYYY-MM-DD format
            target_date = attendance_date if attendance_date else datetime.date.today().isoformat()
            
            # Check if student already has an attendance record for the target date
            c.execute("SELECT id FROM attendance WHERE student_id = ? AND date(timestamp) = ?", 
                      (student_id, target_date))
            existing_record = c.fetchone()
            
            if existing_record:
                # Student already marked attendance for this date - do nothing
                return False
            else:
                # No attendance record for target date - insert new record
                # Create timestamp for the target date (use current time for that date)
                if target_date == datetime.date.today().isoformat():
                    # For today, use current timestamp
                    timestamp = datetime.datetime.utcnow().isoformat()
                else:
                    # For other dates, use the date at noon to avoid timezone issues
                    timestamp = f"{target_date}T12:00:00.000000"
                
                c.execute("INSERT INTO attendance (student_id, name, timestamp) VALUES (?, ?, ?)", 
                          (student_id, name, timestamp))
                conn.commit()
                return True
            
        except sqlite3.IntegrityError:
            # Unique constraint violated - another thread already inserted
            return False
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return False
        finally:
            if conn:
                conn.close()

def cleanup_duplicate_attendance():
    """Remove duplicate attendance records, keeping only the earliest entry per student per day"""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Find duplicates and keep only the earliest entry
        c.execute("""DELETE FROM attendance WHERE id NOT IN (
                     SELECT MIN(id) FROM attendance 
                     GROUP BY student_id, date(timestamp)
                 )""")
        deleted_rows = c.rowcount
        conn.commit()
        return deleted_rows
    except sqlite3.Error as e:
        print(f"Database error cleaning duplicates: {e}")
        return 0
    finally:
        if conn:
            conn.close()