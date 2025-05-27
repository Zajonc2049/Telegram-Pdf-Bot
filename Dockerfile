FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y tesseract-ocr tesseract-ocr-ukr tesseract-ocr-eng libglib2.0-0 libsm6 libxrender1 libxext6 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Створюємо директорії для тимчасових файлів
RUN mkdir -p /app/temp

COPY bot.py .
COPY requirements.txt .
COPY fonts/ ./fonts/

RUN pip install --no-cache-dir -r requirements.txt

# Створюємо користувача для безпеки
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

CMD ["python", "bot.py"]
