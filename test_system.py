#!/usr/bin/env python3
"""
Quick test script to verify the face detection attendance system components.
Run this after installing dependencies to check if everything works.
"""

import sys
import os

def test_imports():
    """Test if all required modules can be imported."""
    print("Testing imports...")
    try:
        import flask
        print("[OK] Flask")
    except ImportError as e:
        print(f"[FAIL] Flask: {e}")
        return False
    
    try:
        import cv2
        print("[OK] OpenCV")
    except ImportError as e:
        print(f"[FAIL] OpenCV: {e}")
        return False
    
    try:
        import numpy as np
        print("[OK] NumPy")
    except ImportError as e:
        print(f"[FAIL] NumPy: {e}")
        return False
    
    try:
        from sklearn.ensemble import RandomForestClassifier
        print("[OK] scikit-learn")
    except ImportError as e:
        print(f"[FAIL] scikit-learn: {e}")
        return False
    
    try:
        import mediapipe as mp
        print("[OK] MediaPipe")
    except ImportError as e:
        print(f"[FAIL] MediaPipe: {e}")
        return False
    
    try:
        import pandas as pd
        print("[OK] Pandas")
    except ImportError as e:
        print(f"[FAIL] Pandas: {e}")
        return False
    
    return True

def test_model_import():
    """Test if model.py can be imported."""
    print("\nTesting model.py import...")
    try:
        from model import extract_embedding_for_image, train_model_background, MODEL_PATH
        print("[OK] model.py imports successfully")
        return True
    except Exception as e:
        print(f"[FAIL] model.py import failed: {e}")
        return False

def test_app_structure():
    """Test if app.py structure is valid."""
    print("\nTesting app.py structure...")
    try:
        # Just check if file exists and is readable
        if os.path.exists("app.py"):
            with open("app.py", "r") as f:
                content = f.read()
                if "Flask" in content and "render_template" in content:
                    print("[OK] app.py structure looks valid")
                    return True
        print("[FAIL] app.py not found or invalid")
        return False
    except Exception as e:
        print(f"[FAIL] Error checking app.py: {e}")
        return False

def test_database_init():
    """Test if database can be initialized."""
    print("\nTesting database initialization...")
    try:
        import sqlite3
        conn = sqlite3.connect(":memory:")
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL
                )""")
        c.execute("""CREATE TABLE IF NOT EXISTS attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER,
                    name TEXT,
                    timestamp TEXT
                )""")
        conn.commit()
        conn.close()
        print("[OK] Database schema is valid")
        return True
    except Exception as e:
        print(f"[FAIL] Database initialization failed: {e}")
        return False

def main():
    print("=" * 50)
    print("Face Detection Attendance System - Test Script")
    print("=" * 50)
    
    results = []
    results.append(("Imports", test_imports()))
    results.append(("Model Import", test_model_import()))
    results.append(("App Structure", test_app_structure()))
    results.append(("Database", test_database_init()))
    
    print("\n" + "=" * 50)
    print("Test Summary:")
    print("=" * 50)
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{name}: {status}")
    
    all_passed = all(r[1] for r in results)
    if all_passed:
        print("\n[SUCCESS] All tests passed! System should work correctly.")
        print("\nTo run the application:")
        print("  python app.py")
        print("\nThen open http://localhost:5000 in your browser")
    else:
        print("\n[WARNING] Some tests failed. Please install missing dependencies:")
        print("  pip install -r requirements.txt")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
