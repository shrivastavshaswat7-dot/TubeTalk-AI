# TubeTalk AI

Chat with a YouTube video. Paste a link and ask questions; answers come only from the video's
transcript and cite the exact moments they come from, so you can jump straight to them in the
player. A learning project that builds a complete, deployed retrieval-augmented generation (RAG)
app on free tiers: Streamlit frontend, FastAPI backend, local embeddings, Supabase pgvector and
Groq. Full specifications are in [`docs/`](docs/).

## Features

- **Process a video:** YouTube URL → English transcript (manual captions preferred) → timestamped
  chunks → embeddings stored in Supabase. Already-processed videos are reused, never duplicated.
- **Grounded answers:** answers use only the transcript. Questions it doesn't cover, and questions
  about other videos, are refused instead of guessed.
- **Timestamp citations:** every answer lists its source moments; clicking one jumps the embedded
  player there (it autoplays where the browser allows), or opens YouTube at that second.
- **Follow-up questions:** "Do modern networks still use it?" is rewritten into a standalone
  question from the conversation before searching; an ambiguous reference gets a clarifying
  question.
- **Conversations per video:** several saved chats per video, kept separate; nothing leaks
  between videos or conversations.
- **Insights:** summary, key takeaways and topics with timestamps, generated once from the full
  transcript; "summarise this video" style questions are answered from them.
- **Light / Dark / System theme** and a layout that works on phones.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit 1.66 (Streamlit Community Cloud) |
| Backend | FastAPI, Pydantic, Uvicorn (Docker on Render) |
| Transcripts | [FreeTranscriptAPI](https://freetranscriptapi.com) (REST, via `requests`) |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (384-d), run locally with FastEmbed / ONNX Runtime |
| Vector store and data | Supabase Postgres + pgvector (exact cosine search) |
| LLM | Groq `openai/gpt-oss-20b` via LangChain |
| Tests | pytest, Streamlit AppTest |

## Architecture

```
Streamlit frontend ──HTTP──▶ FastAPI backend ──▶ Supabase Postgres + pgvector
 (player + chat)              │                    (videos, chunks + embeddings,
                              │                     chat sessions/messages, insights)
                              ├─▶ FreeTranscriptAPI (transcripts)
                              ├─▶ all-MiniLM-L6-v2 (local 384-d embeddings, FastEmbed / ONNX Runtime)
                              └─▶ Groq (openai/gpt-oss-20b via LangChain)
```

The frontend only talks to the backend; all keys stay on the backend.

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

Requirements: Python 3.12, a free [Supabase](https://supabase.com) project, a free
[Groq](https://console.groq.com) API key and a [FreeTranscriptAPI](https://freetranscriptapi.com)
API key (signup includes free credits).

Create a virtual environment (any location works) and install the dependencies:

```powershell
uv venv "$env:USERPROFILE\venvs\tubetalk" --python 3.12
& "$env:USERPROFILE\venvs\tubetalk\Scripts\Activate.ps1"
uv pip install --python "$env:USERPROFILE\venvs\tubetalk\Scripts\python.exe" -r requirements.txt
Copy-Item .env.example backend/.env   # then edit with your own values (git-ignored)
```

Database: run `database/migrations/001_init.sql` and then `002_video_insights.sql` in the
Supabase SQL editor.

`requirements.txt` at the repository root installs everything (backend, embeddings, frontend).
The per-service files in `backend/` and `frontend/` are used for deploying each service on its own.

### Environment variables

Never commit real values: `backend/.env` and `.streamlit/secrets.toml` are git-ignored, and
`.env.example` / `frontend/.streamlit/secrets.toml.example` contain placeholders only.

| Name | Used by | Required | Purpose |
|---|---|---|---|
| `GROQ_API_KEY` | backend | yes | Groq API key |
| `GROQ_MODEL` | backend | yes | Groq model name, e.g. `openai/gpt-oss-20b` |
| `SUPABASE_URL` | backend | yes | Supabase project URL |
| `SUPABASE_KEY` | backend | yes | Supabase **service-role** key (backend only, never the frontend) |
| `FREE_TRANSCRIPT_API_KEY` | backend | yes, to process new videos | FreeTranscriptAPI key; without it, already processed videos still work |
| `API_BASE_URL` | frontend | yes | Backend address, e.g. `http://localhost:8000` locally; without it the app shows a configuration error |
| `ALLOWED_ORIGINS`, `EMBEDDING_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`, `MIN_SIMILARITY`, `FULL_CONTEXT_MAX_TOKENS`, `GROQ_MAX_TOKENS`, `GROQ_REASONING_EFFORT`, `WARMUP_EMBEDDINGS` | backend | no | Tuning; defaults are in `.env.example` |

## Run locally

Two terminals, venv active in both:

```powershell
cd backend ; python -m uvicorn app.main:app --port 8000
```

```powershell
$env:API_BASE_URL = "http://localhost:8000"
cd frontend ; python -m streamlit run app.py
```

Open http://localhost:8501. The frontend reads the backend address from `API_BASE_URL`
(environment variable or `frontend/.streamlit/secrets.toml`, see the `.example` file); if it is
missing, the app shows a configuration error instead of guessing.

## Tests

```powershell
uv pip install --python "$env:USERPROFILE\venvs\tubetalk\Scripts\python.exe" -r requirements-dev.txt
cd frontend ; python -m pytest tests -q ; cd ..
cd backend ; python -m pytest tests -q --ignore=tests/test_api_live.py --ignore=tests/test_db_live.py --ignore=tests/test_insights_live.py --ignore=tests/test_rag_live.py --ignore=tests/test_retrieval_live.py
```

The offline suites mock every external service. The `*_live.py` backend tests use the real Groq
API and FreeTranscriptAPI (spending credits) and write (temporary) rows to Supabase whenever
`backend/.env` is configured, so they are excluded above; run them only on purpose.

## Deployment (free tiers)

- **Backend → Render free web service (Docker).** Embeddings run on ONNX Runtime (FastEmbed), so the
  whole API peaks around 300 MB, within Render's free 512 MB.
  1. New → Web Service → connect this GitHub repository; Language **Docker** (uses the root
     `Dockerfile`), instance type **Free**, health check path `/health`.
  2. Add the environment variables `GROQ_API_KEY`, `GROQ_MODEL`, `SUPABASE_URL`, `SUPABASE_KEY`,
     `FREE_TRANSCRIPT_API_KEY`.
  3. Deploy; `https://<service>.onrender.com/health` should return `healthy`.
- **Frontend → Streamlit Community Cloud.** New app from this GitHub repository, main file
  `frontend/app.py`, Python 3.12, and the secret `API_BASE_URL = "https://<service>.onrender.com"`.
  The frontend only installs `frontend/requirements.txt`.

## Limitations

- **Transcripts come from a third-party service.** YouTube blocks transcript requests from many
  cloud servers, so the backend uses FreeTranscriptAPI. Every lookup uses one credit, including
  lookups for videos without captions; when the credits run out, new videos can't be processed
  (already processed videos keep working). Failed lookups are not retried automatically.
  Already-processed videos are reused and never fetched again.
- **No login.** Anyone with the link can process videos and chat, which spends the Groq quota and
  adds rows to Supabase. Fine for a demo; add authentication before real public use.
- **Groq free tier:** about 8,000 tokens per minute. Long transcripts sent whole (~25-minute
  videos) can hit it after one or two quick questions; the app then asks you to retry shortly.
- **English transcripts only;** auto-generated captions work but misspell names.
- **Long videos** use only the 5 most similar chunks, so some specific details can be missed.
- **Free hosts sleep when idle;** the first request after a pause can take about a minute while
  the backend wakes up.

## Layout

- `backend/` FastAPI app (routes, schemas, services, db, prompts, tests)
- `frontend/` Streamlit app (`app.py`, `views/`, `components/`, `api_client.py`, tests)
- `database/migrations/` SQL migrations
- `Dockerfile` backend container (Render or any Docker host)
- `scripts/` manual experiment scripts (transcript, RAG, insights and retrieval checks against real services)
- `docs/` specifications
