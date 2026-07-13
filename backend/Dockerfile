FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        libpq-dev \
        libreoffice \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-vie \
        tesseract-ocr-chi-sim \
        tesseract-ocr-chi-tra \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-rag.txt requirements-ocr.txt requirements-retrieval.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements-rag.txt || echo "Optional RAG-Anything install failed; fallback parsers remain available."
RUN pip install --no-cache-dir -r requirements-retrieval.txt
RUN pip install --no-cache-dir "pypdfium2>=4.30.0" || echo "Optional pypdfium2 install failed; scanned PDF OCR will be limited."
RUN pip install --no-cache-dir "paddlepaddle>=3.0.0" "paddleocr>=3.0.0" || echo "Optional PaddleOCR install failed; Tesseract OCR remains available."
RUN pip install --no-cache-dir "vietocr>=0.3.13" || echo "Optional VietOCR install failed; Tesseract OCR remains available."

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
