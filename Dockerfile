FROM python:3.10-slim

# 1. Установка системных зависимостей (добавлены библиотеки для OpenCV)
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Обновление инструментов сборки (важно для dlib)
RUN pip install --upgrade pip setuptools wheel

# 3. Установка зависимостей Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Копирование кода
COPY . .

# 5. Команда запуска сервера (FastAPI)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
