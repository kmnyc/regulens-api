FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Pre-download ONNX model at build time so Render startup is instant
RUN python -c "from fastembed import TextEmbedding; list(TextEmbedding('sentence-transformers/all-MiniLM-L6-v2').embed(['warmup']))"
COPY app.py .
COPY src/ ./src/
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
