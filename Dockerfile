FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y tesseract-ocr tesseract-ocr-ukr tesseract-ocr-eng libglib2.0-0 libsm6 libxrender1 libxext6 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY bot.py .
COPY requirements.txt .
COPY fonts/ ./fonts/

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "bot.py"]
