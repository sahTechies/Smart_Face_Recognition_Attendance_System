import cv2
import mediapipe as mp
import numpy as np
from flask import Response
import threading
import time

# Initialize MediaPipe Face Detection with Crowd Mode settings
mp_face_detection = mp.solutions.face_detection
mp_drawing = mp.solutions.drawing_utils

# Configure for crowd mode (long-range detection)
face_detection = mp_face_detection.FaceDetection(
    model_selection=1,  # Long-range model for detecting small faces
    min_detection_confidence=0.5  # Balanced sensitivity for classroom environment
)

def generate_frames():
    """
    Flask video streaming generator with Crowd Mode and Frame Skipping optimization.
    
    Features:
    1. Crowd Mode: Uses MediaPipe with model_selection=1 for detecting small faces
    2. Frame Skipping: Runs heavy detection only once every 30 frames (1 second)
    3. Smooth streaming: Yields raw frames immediately on non-detection frames
    
    Returns:
        Generator yielding JPEG encoded frames for Flask Response
    """
    # Initialize camera
    cap = cv2.VideoCapture(0)  # Use 0 for default camera, or camera index
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    
    # Frame counter for skipping logic
    frame_counter = 0
    DETECTION_INTERVAL = 30  # Run detection every 30 frames (~1 second at 30 FPS)
    
    # Load trained model for face recognition
    from model import load_model_if_exists, predict_with_model
    clf = load_model_if_exists()
    
    # Track recently detected faces to prevent duplicate processing
    processed_faces = {}
    last_cleanup_time = time.time()
    
    try:
        while True:
            success, frame = cap.read()
            if not success:
                print("Camera read failed")
                break
            
            frame_counter += 1
            current_time = time.time()
            
            # ---------------- FRAME SKIPPING LOGIC ----------------
            # Skip heavy face detection on most frames to maintain smooth video
            should_detect = (frame_counter % DETECTION_INTERVAL == 0)
            
            if should_detect:
                # HEAVY PROCESSING FRAME: Run face detection and recognition
                print(f"Detection frame #{frame_counter}")  # Debug output
                
                # Convert BGR to RGB for MediaPipe
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Process frame with MediaPipe Face Detection
                results = face_detection.process(rgb_frame)
                
                detected_faces = []
                
                if results.detections:
                    for detection in results.detections:
                        # Get bounding box coordinates
                        bbox = detection.location_data.relative_bounding_box
                        h, w, _ = frame.shape
                        
                        # Convert relative coordinates to absolute pixels
                        x1 = int(bbox.xmin * w)
                        y1 = int(bbox.ymin * h)
                        x2 = int((bbox.xmin + bbox.width) * w)
                        y2 = int((bbox.ymin + bbox.height) * h)
                        
                        # Ensure coordinates are within frame bounds
                        x1 = max(0, x1)
                        y1 = max(0, y1)
                        x2 = min(w, x2)
                        y2 = min(h, y2)
                        
                        if x2 > x1 and y2 > y1:
                            # Extract face region
                            face_roi = frame[y1:y2, x1:x2]
                            
                            if face_roi.size > 0:
                                # Generate embedding for face recognition
                                face_embedding = None
                                try:
                                    # Convert to grayscale and resize for model
                                    face_gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
                                    face_resized = cv2.resize(face_gray, (32, 32), interpolation=cv2.INTER_AREA)
                                    face_embedding = face_resized.flatten().astype(np.float32) / 255.0
                                except Exception as e:
                                    print(f"Face processing error: {e}")
                                
                                # Recognize face if model is available
                                student_name = "Unknown"
                                student_id = None
                                confidence = 0.0
                                
                                if face_embedding is not None and clf is not None:
                                    try:
                                        student_id, confidence = predict_with_model(clf, face_embedding)
                                        
                                        # Get student name from database
                                        if confidence > 0.5:  # Confidence threshold
                                            import sqlite3
                                            import os
                                            APP_DIR = os.path.dirname(os.path.abspath(__file__))
                                            DB_PATH = os.path.join(APP_DIR, "attendance.db")
                                            
                                            conn = sqlite3.connect(DB_PATH)
                                            c = conn.cursor()
                                            c.execute("SELECT name FROM students WHERE id=?", (int(student_id),))
                                            row = c.fetchone()
                                            student_name = row[0] if row else f"Student {student_id}"
                                            conn.close()
                                    except Exception as e:
                                        print(f"Recognition error: {e}")
                                
                                # Store face info for drawing
                                detected_faces.append({
                                    'bbox': (x1, y1, x2, y2),
                                    'name': student_name,
                                    'confidence': confidence,
                                    'student_id': student_id
                                })
                                
                                # Mark attendance if recognized and not recently processed
                                if student_id and confidence > 0.5:
                                    face_key = f"{student_id}_{int(current_time // 60)}"  # Key per student per minute
                                    if face_key not in processed_faces:
                                        try:
                                            from attendance_utils import mark_attendance
                                            attendance_marked = mark_attendance(int(student_id), student_name)
                                            if attendance_marked:
                                                print(f"Attendance marked for {student_name}")
                                        except Exception as e:
                                            print(f"Attendance marking error: {e}")
                                        
                                        processed_faces[face_key] = current_time
                
                # Draw bounding boxes and labels on frame
                for face_info in detected_faces:
                    x1, y1, x2, y2 = face_info['bbox']
                    name = face_info['name']
                    confidence = face_info['confidence']
                    
                    # Draw bounding box
                    color = (0, 255, 0) if confidence > 0.5 else (0, 0, 255)  # Green for recognized, red for unknown
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    
                    # Draw label with name and confidence
                    label = f"{name}: {confidence:.2f}"
                    label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
                    cv2.rectangle(frame, (x1, y1 - 25), (x1 + label_size[0], y1), color, -1)
                    cv2.putText(frame, label, (x1, y1 - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                
                # Add detection indicator
                cv2.putText(frame, f"DETECTING ({len(detected_faces)} faces)", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            else:
                # ---------------- SKIP FRAME LOGIC ----------------
                # LIGHTWEIGHT FRAME: Skip detection, just yield raw frame for smooth video
                # This prevents lag by not running heavy MediaPipe + recognition on every frame
                
                # Add frame skip indicator
                cv2.putText(frame, f"STREAMING (frame {frame_counter % DETECTION_INTERVAL}/{DETECTION_INTERVAL})", 
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
            
            # Clean up old face entries every 5 seconds
            if current_time - last_cleanup_time > 5:
                processed_faces = {k: v for k, v in processed_faces.items() if current_time - v < 300}  # Keep 5 minutes
                last_cleanup_time = current_time
            
            # Add frame info
            fps_text = f"FPS: {int(cap.get(cv2.CAP_PROP_FPS))}"
            cv2.putText(frame, fps_text, (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Add mode indicator
            mode_text = "CROWD MODE | LONG RANGE DETECTION"
            cv2.putText(frame, mode_text, (10, frame.shape[0] - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            
            # Encode frame to JPEG
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            frame_bytes = buffer.tobytes()
            
            # Yield frame for Flask streaming
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
    except Exception as e:
        print(f"Video streaming error: {e}")
    finally:
        # Cleanup
        cap.release()
        face_detection.close()

# Flask route for video streaming
@app.route('/video_feed')
def video_feed():
    """Video streaming route with optimized crowd mode and frame skipping."""
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')