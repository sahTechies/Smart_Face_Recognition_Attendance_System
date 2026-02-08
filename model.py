import os
import cv2
import numpy as np
import pickle
from sklearn.ensemble import RandomForestClassifier

MODEL_PATH = "model.pkl"

# ---- Utility: extract face crop -> small grayscale vector (embedding) ----
# Note: This function is kept for backward compatibility but is no longer used
# since we switched from MediaPipe to OpenCV face detection
def crop_face_and_embed(bgr_image, detection):
    # Legacy function - not used anymore but kept for compatibility
    h, w = bgr_image.shape[:2]
    if hasattr(detection, 'location_data'):
        bbox = detection.location_data.relative_bounding_box
        x1 = int(max(0, bbox.xmin * w))
        y1 = int(max(0, bbox.ymin * h))
        x2 = int(min(w, (bbox.xmin + bbox.width) * w))
        y2 = int(min(h, (bbox.ymin + bbox.height) * h))
    else:
        # Handle OpenCV detection format (x, y, w, h)
        x1, y1, w_det, h_det = detection
        x2 = x1 + w_det
        y2 = y1 + h_det
    if x2 <= x1 or y2 <= y1:
        return None
    face = bgr_image[y1:y2, x1:x2]
    face = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    face = cv2.resize(face, (32,32), interpolation=cv2.INTER_AREA)
    emb = face.flatten().astype(np.float32) / 255.0
    return emb

def extract_embedding_for_image(stream_or_bytes):
    # accepts a file-like stream (werkzeug FileStorage.stream)
    # Using OpenCV's DNN face detector as fallback since MediaPipe API changed
    import cv2
    
    # Read image from stream
    data = stream_or_bytes.read()
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    
    # Use OpenCV's Haar Cascade or DNN for face detection
    # Load face detector
    face_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_cascade = cv2.CascadeClassifier(face_cascade_path)
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.1, 4)
    
    if len(faces) == 0:
        return None
    
    # Use the first detected face
    x, y, w, h = faces[0]
    face = img[y:y+h, x:x+w]
    face = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    face = cv2.resize(face, (32,32), interpolation=cv2.INTER_AREA)
    emb = face.flatten().astype(np.float32) / 255.0
    return emb

# ---- Load model helpers ----
def load_model_if_exists():
    if not os.path.exists(MODEL_PATH):
        return None
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)

def predict_with_model(clf, emb):
    # returns label and confidence (max probability)
    proba = clf.predict_proba([emb])[0]
    idx = np.argmax(proba)
    label = clf.classes_[idx]
    conf = float(proba[idx])
    return label, conf

# ---- Training function used in background ----
def train_model_background(dataset_dir, progress_callback=None):
    """
    dataset_dir/
        student_id/
            img1.jpg
            img2.jpg
    progress_callback(progress_percent, message) -> optional
    """
    try:
        # Using OpenCV's Haar Cascade for face detection (more compatible)
        face_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        face_cascade = cv2.CascadeClassifier(face_cascade_path)

        X = []
        y = []
        
        if not os.path.exists(dataset_dir):
            if progress_callback:
                progress_callback(0, "Dataset directory not found")
            return
        
        student_dirs = [d for d in os.listdir(dataset_dir) if os.path.isdir(os.path.join(dataset_dir, d))]
        
        if len(student_dirs) == 0:
            if progress_callback:
                progress_callback(0, "No students found. Add students first.")
            return
        
        total_students = len(student_dirs)
        processed = 0

        if progress_callback:
            progress_callback(5, f"Found {total_students} student(s). Processing images...")

        for sid in student_dirs:
            folder = os.path.join(dataset_dir, sid)
            if not os.path.exists(folder):
                processed += 1
                continue
                
            files = [f for f in os.listdir(folder) if f.lower().endswith((".jpg",".jpeg",".png"))]
            
            if len(files) == 0:
                processed += 1
                if progress_callback:
                    pct = int((processed/total_students)*80)
                    progress_callback(pct, f"Student {sid}: No images found")
                continue
            
            for fn in files:
                path = os.path.join(folder, fn)
                img = cv2.imread(path)
                if img is None:
                    continue
                
                # Use OpenCV face detection
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.1, 4)
                
                if len(faces) == 0:
                    continue
                
                # Use the first detected face
                # Note: using fx, fy, fw, fh to avoid overwriting the y list variable
                fx, fy, fw, fh = faces[0]
                face = img[fy:fy+fh, fx:fx+fw]
                face = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
                face = cv2.resize(face, (32,32), interpolation=cv2.INTER_AREA)
                emb = face.flatten().astype(np.float32) / 255.0
                
                if emb is None:
                    continue
                X.append(emb)
                y.append(int(sid))
            
            processed += 1
            if progress_callback:
                pct = int((processed/total_students)*80)  # training progress up to 80% during feature extraction
                progress_callback(pct, f"Processed {processed}/{total_students} students ({len(X)} images)")

        if len(X) == 0:
            if progress_callback:
                progress_callback(0, "No training data found. Make sure students have face images.")
            return

        # convert
        X = np.stack(X)
        y = np.array(y)

        # fit RandomForest
        if progress_callback:
            progress_callback(85, f"Training RandomForest with {len(X)} samples...")
        clf = RandomForestClassifier(n_estimators=150, n_jobs=-1, random_state=42)
        clf.fit(X, y)

        with open(MODEL_PATH, "wb") as f:
            pickle.dump(clf, f)

        if progress_callback:
            progress_callback(100, "Training complete!")
    except Exception as e:
        import traceback
        error_msg = f"Training error: {str(e)}"
        if progress_callback:
            progress_callback(0, error_msg)
        print(f"Training error: {traceback.format_exc()}")
