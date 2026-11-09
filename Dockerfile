# TubeTalk AI backend (FastAPI + local embeddings) for any Docker host; set up for a Hugging Face
# Docker Space (free CPU tier has enough memory for PyTorch; the API listens on $PORT, default 7860).
# Secrets (GROQ_API_KEY, GROQ_MODEL, SUPABASE_URL, SUPABASE_KEY) come from the host's settings,
# never from the image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860

# Hugging Face Spaces run the container as user 1000.
RUN useradd -m -u 1000 user
WORKDIR /home/user/app

# CPU-only PyTorch first, so sentence-transformers does not pull the multi-GB CUDA build.
COPY backend/requirements.txt backend/requirements-embeddings.txt ./
RUN pip install --no-cache-dir torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements-embeddings.txt

COPY --chown=user backend/app ./app
USER user
ENV HOME=/home/user HF_HOME=/home/user/.cache/huggingface

# Bake the embedding model into the image so a cold start does not download it.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
