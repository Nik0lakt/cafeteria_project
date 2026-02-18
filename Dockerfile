FROM python:3.10-slim

# Устанавливаем системные зависимости для OpenCV, Git и компиляции dlib
RUN apt-get update && apt-get install -y \
    git \
    cmake \
    g++ \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Устанавливаем зависимости Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir git+https://github.com/ageitgey/face_recognition_models

# Копируем остальной код
COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
