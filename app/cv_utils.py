import os
import face_recognition
import numpy as np
import cv2

EAR_CLOSE_THRESHOLD = 0.22   # начало фазы «глаз закрывается»
EAR_OPEN_THRESHOLD  = 0.27   # конец фазы — глаз открылся снова
EAR_MIN_BLINK       = 0.18   # реальное моргание на веб-камере: 0.05–0.18; наклон фото: 0.19–0.22 → не засчитается

# Чем выше — тем мягче проверка. 0.6 — дефолт face_recognition, 0.45 — очень строго.
FACE_TOLERANCE = float(os.getenv('FACE_RECOGNITION_TOLERANCE', '0.55'))


def _compute_ear(eye):
    a = np.linalg.norm(np.array(eye[1]) - np.array(eye[5]))
    b = np.linalg.norm(np.array(eye[2]) - np.array(eye[4]))
    c = np.linalg.norm(np.array(eye[0]) - np.array(eye[3]))
    return (a + b) / (2.0 * c) if c > 1e-6 else 0.0


def get_face_embedding_and_ear(image_bytes):
    """Returns (embedding, ear) — detects face once, computes both."""
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None, None
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        face_locations = face_recognition.face_locations(rgb_img)
        if not face_locations:
            return None, None

        encodings = face_recognition.face_encodings(rgb_img, known_face_locations=face_locations)
        embedding = encodings[0] if encodings else None

        ear = None
        landmarks_list = face_recognition.face_landmarks(rgb_img, face_locations=face_locations)
        if landmarks_list:
            lm = landmarks_list[0]
            ear = (_compute_ear(lm['left_eye']) + _compute_ear(lm['right_eye'])) / 2.0

        return embedding, ear
    except Exception as e:
        print(f"CV Error: {e}")
        return None, None


def get_face_embedding(image_bytes):
    embedding, _ = get_face_embedding_and_ear(image_bytes)
    return embedding


def compare_faces(embedding1, embedding2, tolerance=None):
    if tolerance is None:
        tolerance = FACE_TOLERANCE
    try:
        dist = face_recognition.face_distance([embedding1], embedding2)[0]
        result = bool(dist <= tolerance)
        print(f"[FACE] distance={dist:.4f}  tolerance={tolerance}  match={result}")
        return result
    except Exception as e:
        print(f"Comparison Error: {e}")
        return False
