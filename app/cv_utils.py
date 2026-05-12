import face_recognition
import numpy as np
import cv2

def get_face_embedding(image_bytes):
    try:
        # Декодируем изображение из байтов
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None
            
        # Конвертируем в RGB (face_recognition работает с RGB)
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # Ищем лица и создаем эмбеддинги
        encodings = face_recognition.face_encodings(rgb_img)
        
        if len(encodings) > 0:
            return encodings[0]
        return None
    except Exception as e:
        print(f"CV Error: {e}")
        return None

def compare_faces(embedding1, embedding2, tolerance=0.45):
    try:
        dist = face_recognition.face_distance([embedding1], embedding2)[0]
        result = bool(dist <= tolerance)
        print(f"[FACE] distance={dist:.4f}  tolerance={tolerance}  match={result}")
        return result
    except Exception as e:
        print(f"Comparison Error: {e}")
        return False
