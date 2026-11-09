# TubeTalk AI
# Deployment Guide

**Version:** 1.0  
**Status:** Proposed  
**Frontend Hosting:** Streamlit Community Cloud  
**Backend Hosting:** Render (Docker, free)\
**Database:** Supabase

## 1. Introduction

This document defines the deployment strategy for TubeTalk AI.

The frontend, backend, and database will operate as separate services.

## 2. Deployment Architecture

### Frontend

Streamlit Community Cloud.

Responsibilities:

- Host the user interface.
- Communicate with the backend.
- Display video information and AI responses.

### Backend

Render free web service, built from the repository `Dockerfile`. Embeddings run locally on ONNX
Runtime (FastEmbed, no PyTorch), so the API peaks around 300 MB of RAM, within the free 512 MB.

Responsibilities:

- Run the FastAPI application.
- Handle transcript processing.
- Execute RAG operations.
- Communicate with Supabase.
- Communicate with Groq.

### Database

Supabase.

Responsibilities:

- Store application records.
- Store chat history.
- Store transcript chunks.
- Store vector embeddings.

## 3. Prerequisites

Before deployment:

- GitHub repository.
- Working local application.
- Supabase project.
- Groq API key.
- requirements.txt.
- Environment configuration.
- Successful local testing.

## 4. Backend Deployment

The repository contains everything the service needs:

- `Dockerfile` (repository root): Python 3.12, the backend requirements (FastEmbed / ONNX Runtime),
  the embedding model downloaded at build time, and `uvicorn app.main:app` on `$PORT` (set by Render).
- `.dockerignore`: keeps `.env` files, secrets and non-backend folders out of the build.

### Step 1: Create the Web Service

In Render: New → Web Service → connect the GitHub repository. Choose Language **Docker** (root
`Dockerfile`), instance type **Free**, and health check path `/health`.

### Step 2: Configure Environment Variables

In the service's Environment settings, add:

- GROQ_API_KEY
- GROQ_MODEL (for example `openai/gpt-oss-20b`)
- SUPABASE_URL
- SUPABASE_KEY (service-role key; backend only)

Never upload secret credentials into GitHub.

### Step 3: Deploy and Verify

Render builds the image and serves the API at `https://<service>.onrender.com`.

Verify:

- Backend starts successfully.
- Health endpoint works.
- API documentation loads.
- Database connection works.
- LLM integration works.

## 5. Frontend Deployment

### Step 1: Prepare Frontend

Ensure the Streamlit application is working locally.

### Step 2: Push Code to GitHub

Push the latest tested code.

### Step 3: Create Streamlit Cloud Application

Connect the GitHub repository.

Select the frontend entry-point file and Python 3.12:

```text
frontend/app.py
```

Streamlit Cloud installs `frontend/requirements.txt` (Streamlit and requests only) and
reads the theme from `frontend/.streamlit/config.toml`.

### Step 4: Configure Secrets

Add the backend API URL through the Streamlit secrets configuration.

Example:

```toml
API_BASE_URL = "https://<service>.onrender.com"
```

Do not expose backend API credentials through frontend configuration.

### Step 5: Deploy

Start the deployment and verify that the frontend loads successfully.

## 6. Supabase Configuration

Before deployment:

1. Create a Supabase project.
2. Enable pgvector.
3. Execute the database schema.
4. Create required tables.
5. Configure foreign keys.
6. Configure indexes.
7. Test database connectivity.
8. Review access policies.

Use backend-side credentials for database operations.

Do not expose service-role credentials to Streamlit.

## 7. Environment Variables

### Backend

```env
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-20b
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_backend_database_key
```

### Frontend

```env
API_BASE_URL=your_backend_api_url
```

Actual secret values must never be committed to version control.

The example values above are placeholders.

## 8. CORS Configuration

The Streamlit app calls the backend from the Streamlit server, not from the browser, so CORS does
not block it. `ALLOWED_ORIGINS` only matters for browser-based clients; if one is added, set it to
that client's actual URL.

Avoid unrestricted CORS in production unless there is a justified requirement.

## 9. Production Verification

After deployment, verify:

- Frontend opens.
- Backend health endpoint responds.
- YouTube URL processing works.
- Transcript extraction works.
- Embeddings are generated.
- Database records are saved.
- Semantic retrieval works.
- Groq generates responses.
- Chat history persists.
- Previous sessions can be restored.
- Timestamp links work.
- Error handling works.

## 10. Deployment Security

- Keep all API keys private.
- Use environment variables.
- Never commit .env files.
- Configure database access carefully.
- Use HTTPS endpoints.
- Restrict CORS.
- Validate incoming requests.
- Avoid returning internal stack traces to users.

## 11. Deployment Limitations

Free hosting services may have:

- Usage limits.
- Sleep or cold-start behavior.
- Resource restrictions.
- Request timeouts.
- Storage limitations.

The selected services and their current free-tier policies must be verified before production deployment.

The local application should remain runnable independently of hosting availability.

## 12. Maintenance

Future maintenance tasks:

- Monitor service logs.
- Review API failures.
- Monitor Groq usage.
- Check database usage.
- Update dependencies.
- Back up important data.
- Test after deployments.
- Fix security vulnerabilities.

## 13. Conclusion

TubeTalk AI will use a separate frontend, backend, and database deployment architecture.

Streamlit Community Cloud will host the frontend, a Render free web service will host FastAPI, and Supabase will provide persistent PostgreSQL and vector storage.

The application will be deployed only after critical features have been tested locally.

**TubeTalk AI — Deploy Carefully. Maintain Continuously.**