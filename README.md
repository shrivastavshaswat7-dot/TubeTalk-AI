# TubeTalk AI

Chat with a YouTube video. Paste a link and ask questions; answers come only from the video's
transcript and cite the exact moments they come from. A learner-level GenAI project built with a
basic RAG pipeline: Streamlit frontend, FastAPI backend, LangChain, Hugging Face embeddings,
Supabase pgvector and Groq. Full specs are in [`docs/`](docs/).

## Features

- **Process a video:** YouTube URL → English transcript (manual captions preferred) → stored and searchable.
- **Grounded answers:** answers use only the transcript; questions it doesn't cover are refused honestly.
- **Timestamp citations:** every answer cites its source moments; click one to jump the embedded player there (it autoplays where the browser allows).
- **Follow-up questions:** "What is cool about them?" is understood from the conversation.
- **Conversations per video:** several chats per video, kept separate; nothing leaks between videos.
- **Insights:** summary, key takeaways and topics with timestamps; "summarise this video" uses them.
- **Light / Dark / System theme.**

## Architecture

```
Streamlit frontend ──HTTP──▶ FastAPI backend ──▶ Supabase Postgres + pgvector
 (player + chat)              │                    (videos, chunks + embeddings,
                              │                     chat sessions/messages, insights)
                              ├─▶ youtube-transcript-api (transcripts)
                              ├─▶ all-MiniLM-L6-v2 (local 384-d embeddings, sentence-transformers)
                              └─▶ Groq (openai/gpt-oss-20b via LangChain)
```

RAG flow for one question:

1. **Ingestion (once per video):** transcript → ~800-character chunks with 150-character overlap
   that keep their start/end times → embeddings → `transcript_chunks` in Supabase.
2. **Follow-up handling:** with earlier messages, the question is rewritten into a standalone one
   (one Groq call); retrieval stays anchored to the conversation if the rewrite fails.
3. **Context:** short transcripts (≤ ~6,000 tokens) are passed whole; longer ones use the 5 most
   similar chunks of *this video only* (exact cosine search in pgvector).
4. **Answer:** Groq answers from the numbered excerpts only and cites them as `[C1]`; citations
   are replaced with the real chunk timestamps. If the excerpts don't contain the answer, the model
   says so and the app shows a refusal instead of guessing.
5. **Whole-video questions** ("what is this video about?") are answered from the stored Insights.

## Setup (Windows, PowerShell)

Create a Python 3.12 virtual environment (any location works) and install the dependencies:

```powershell
uv venv "$env:USERPROFILE\venvs\tubetalk" --python 3.12
& "$env:USERPROFILE\venvs\tubetalk\Scripts\Activate.ps1"
uv pip install --python "$env:USERPROFILE\venvs\tubetalk\Scripts\python.exe" -r requirements.txt
Copy-Item .env.example backend/.env   # then edit with real values (git-ignored)
```

`backend/.env` needs `GROQ_API_KEY`, `GROQ_MODEL` (e.g. `openai/gpt-oss-20b`), `SUPABASE_URL` and
`SUPABASE_KEY` (service-role key, backend only). Database: run `database/migrations/001_init.sql`
and `002_video_insights.sql` in the Supabase SQL editor.

`requirements.txt` at the repository root installs everything (backend, embeddings, frontend).
The per-service files in `backend/` and `frontend/` are used for deploying each service on its own.

## Run locally

Two terminals, venv active in both:

```powershell
cd backend ; python -m uvicorn app.main:app --port 8000
```

```powershell
cd frontend ; python -m streamlit run app.py
```

Open http://localhost:8501. The frontend reads the backend address from `API_BASE_URL`
(environment variable or Streamlit secrets), defaulting to `http://localhost:8000`.

## Tests

```powershell
uv pip install --python "$env:USERPROFILE\venvs\tubetalk\Scripts\python.exe" -r requirements-dev.txt
cd frontend ; python -m pytest tests -q ; cd ..
cd backend ; python -m pytest tests -q --ignore=tests/test_api_live.py --ignore=tests/test_db_live.py --ignore=tests/test_insights_live.py --ignore=tests/test_rag_live.py --ignore=tests/test_retrieval_live.py
```

The `*_live.py` backend tests use the real Groq API and write (temporary) rows to Supabase whenever
`backend/.env` is configured, so they are excluded above; run them only on purpose.

## Deployment (free tiers)

- **Backend → Hugging Face Space (Docker, free CPU).** PyTorch plus the embedding model need about
  600 MB of RAM, more than Render's free 512 MB.
  1. Create a new Space with the **Docker** SDK (blank template).
  2. In the Space settings, add the secrets `GROQ_API_KEY`, `GROQ_MODEL`, `SUPABASE_URL`, `SUPABASE_KEY`.
  3. Upload the `Dockerfile`, `backend/app/`, `backend/requirements.txt`,
     `backend/requirements-embeddings.txt`, and `deploy/hf-space/README.md` **as the Space's `README.md`**
     (it holds the Space configuration: Docker SDK, port 7860).
  4. Wait for the build; `https://<user>-<space>.hf.space/health` should return `healthy`.
- **Frontend → Streamlit Community Cloud.** New app from this GitHub repository, main file
  `frontend/app.py`, Python 3.12, and the secret `API_BASE_URL = "https://<user>-<space>.hf.space"`.
  The frontend only installs `frontend/requirements.txt` (no PyTorch).

## Limitations

- **No login.** Anyone with the link can process videos and chat, which spends the Groq quota and
  adds rows to Supabase. Fine for a demo; add authentication before real public use.
- **YouTube often blocks transcript requests from cloud servers.** If processing a new video fails
  on the deployed app with "YouTube blocked the transcript request", process it from a local run
  (same Supabase database); it then appears in the deployed app.
- **Groq free tier:** about 8,000 tokens per minute. Long transcripts sent whole (~25-minute videos)
  can hit it after one or two quick questions; the app then asks you to retry shortly.
- **English transcripts only;** auto-generated captions work but misspell names.
- **Long videos** use only the 5 most similar chunks, so some specific details can be missed.
- **Free hosts sleep when idle;** the first request after a pause can take a minute.

## Layout

- `backend/` FastAPI app (routes, schemas, services, db, prompts, tests)
- `frontend/` Streamlit app (`app.py`, `views/`, `components/`, `api_client.py`, tests)
- `database/migrations/` SQL migrations
- `Dockerfile`, `deploy/hf-space/` backend deployment
- `scripts/` manual experiment scripts (transcript, RAG, insights and retrieval checks against real services)
- `docs/` specifications
