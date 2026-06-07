import os

import cv2
import face_recognition
import numpy as np

# Чем выше — тем мягче проверка. 0.6 — дефолт face_recognition, 0.45 — очень строго.
FACE_TOLERANCE = float(os.getenv('FACE_RECOGNITION_TOLERANCE', '0.55'))


def get_face_embedding(image_bytes):
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_img)
        if not face_locations:
            return None
        encodings = face_recognition.face_encodings(rgb_img, known_face_locations=face_locations)
        return encodings[0] if encodings else None
    except Exception as e:
        print(f"CV Error: {e}")
        return None


def compare_faces(embedding1, embedding2, tolerance=None):
    """Returns (match: bool, distance: float)."""
    if tolerance is None:
        tolerance = FACE_TOLERANCE
    try:
        dist = float(face_recognition.face_distance([embedding1], embedding2)[0])
        result = dist <= tolerance
        print(f"[FACE] distance={dist:.4f}  tolerance={tolerance}  match={result}")
        return result, dist
    except Exception as e:
        print(f"Comparison Error: {e}")
        return False, 1.0
