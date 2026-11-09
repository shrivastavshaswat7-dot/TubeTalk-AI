# TubeTalk AI backend (FastAPI + local embeddings) for any Docker host, e.g. Render's free web service.
# Embeddings run on ONNX Runtime (FastEmbed), so the API fits in 512 MB. It listens on $PORT
# (set by the host; 7860 if unset). Secrets (GROQ_API_KEY, GROQ_MODEL, SUPABASE_URL, SUPABASE_KEY)
# come from the host's settings, never from the image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860

RUN useradd -m -u 1000 user
WORKDIR /home/user/app

COPY backend/requirements.txt backend/requirements-embeddings.txt ./
RUN pip install --no-cache-dir -r requirements-embeddings.txt

COPY --chown=user backend/app ./app
USER user
ENV HOME=/home/user FASTEMBED_CACHE_PATH=/home/user/.cache/fastembed

# Bake the embedding model into the image so a cold start does not download it.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/all-MiniLM-L6-v2')"

EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
