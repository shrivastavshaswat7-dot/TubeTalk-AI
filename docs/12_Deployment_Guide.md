# TubeTalk AI
# Deployment Guide

**Version:** 1.0  
**Status:** Proposed  
**Frontend Hosting:** Streamlit Community Cloud  
**Backend Hosting:** Render  
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

Render.

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

### Step 1: Prepare Backend

Ensure the backend contains:

- FastAPI application.
- requirements.txt.
- Correct application entry point.
- Environment variable configuration.

### Step 2: Push Code to GitHub

Commit and push the working backend code.

### Step 3: Create Render Service

Create a new web service connected to the GitHub repository.

Select the backend directory as the service root directory when using a monorepo.

### Step 4: Configure Commands

Build command:

```bash
pip install -r requirements.txt
```

Start command example:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

The exact import path will depend on the final backend directory structure.

### Step 5: Configure Environment Variables

Add required environment variables through Render's dashboard.

Expected variables:

- GROQ_API_KEY
- SUPABASE_URL
- SUPABASE_KEY

Never upload secret credentials into GitHub.

### Step 6: Deploy and Verify

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

Select the frontend entry-point file.

Example:

```text
frontend/app.py
```

### Step 4: Configure Secrets

Add the backend API URL through the Streamlit secrets configuration.

Example:

```toml
API_BASE_URL = "https://your-backend-domain.com"
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

FastAPI must allow requests from the deployed Streamlit frontend.

Configure the allowed origins to include the actual frontend URL.

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

Streamlit Community Cloud will host the frontend, Render will host FastAPI, and Supabase will provide persistent PostgreSQL and vector storage.

The application will be deployed only after critical features have been tested locally.

**TubeTalk AI — Deploy Carefully. Maintain Continuously.**