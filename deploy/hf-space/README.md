---
title: TubeTalk AI API
emoji: 🎬
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# TubeTalk AI — backend API

FastAPI backend of TubeTalk AI, a learner-level YouTube RAG chatbot:
transcript → chunks → local MiniLM embeddings → Supabase pgvector → Groq answer with timestamp citations.

The Streamlit frontend is deployed separately and calls this API. Health check: `GET /health`.

Required Space secrets (Settings → Variables and secrets): `GROQ_API_KEY`, `GROQ_MODEL`,
`SUPABASE_URL`, `SUPABASE_KEY`.

This file is the Space's README (it carries the Space configuration). It is uploaded together with
the repository's `Dockerfile` and `backend/` — see the main project README, "Deployment".
