# Technology Stack
# TubeTalk AI
# Technology Stack & Dependencies

**Project Name:** TubeTalk AI  
**Document Type:** Technology Stack & Dependencies  
**Version:** 1.0  
**Status:** Proposed  
**Project Category:** AI Engineering / Generative AI

---

# 1. Introduction

## 1.1 Purpose

This document defines the technologies, frameworks, libraries, and external services required to develop TubeTalk AI.

It explains the purpose of each technology, why it has been selected, its role in the application, and the knowledge required before implementation.

## 1.2 Technology Selection Principles

The technology stack is selected based on:

1. Ease of learning and implementation.
2. Compatibility with Python-based AI development.
3. Availability of free or affordable development options.
4. Integration capabilities.
5. Industry relevance.
6. Future scalability.
7. Maintainability.

---

# 2. Complete Technology Stack

| Layer | Selected Technology |
|---|---|
| Frontend | Streamlit |
| Backend | Python + FastAPI |
| RAG Framework | LangChain |
| Transcript Extraction | YouTube Transcript API |
| Text Processing | LangChain Text Splitters |
| Embeddings | Hugging Face Sentence Transformers |
| Embedding Model | all-MiniLM-L6-v2 |
| Vector Database | Supabase pgvector |
| Relational Database | Supabase PostgreSQL |
| LLM Provider | Groq |
| LLM Integration | LangChain Groq |
| Backend Server | Uvicorn |
| Frontend Hosting | Streamlit Community Cloud |
| Backend Hosting | Render |
| Version Control | Git + GitHub |
| Development Environment | VS Code |

---

# 3. Frontend Technologies

## 3.1 Streamlit

**Category:** Python Web Application Framework

**Purpose:** Develop the user interface of TubeTalk AI.

Responsibilities:

- YouTube URL input.
- Video information display.
- Video preview.
- Chat interface.
- Conversation history.
- Summary display.
- Key takeaway display.
- Timestamp references.
- Navigation between video sessions.

Why Streamlit?

- Uses Python instead of requiring extensive JavaScript knowledge.
- Provides built-in chat components.
- Simplifies AI application development.
- Supports rapid prototyping.
- Integrates easily with Python libraries.

Knowledge Required:

- Python fundamentals.
- Functions and modules.
- Streamlit layouts.
- Text inputs and buttons.
- Session state.
- Chat message components.
- API requests.

Official Documentation:

https://docs.streamlit.io/

---

# 4. Backend Technologies

## 4.1 Python

**Category:** Programming Language

Python will be the primary programming language for TubeTalk AI.

Responsibilities:

- Application logic.
- Transcript processing.
- RAG pipeline implementation.
- Embedding generation.
- Database interaction.
- LLM integration.
- API development.

Why Python?

Python has a strong ecosystem for Artificial Intelligence, Machine Learning, NLP, and Generative AI.

Knowledge Required:

- Variables and data types.
- Conditional statements.
- Loops.
- Functions.
- Lists, dictionaries, tuples, and sets.
- File handling.
- Exception handling.
- Object-Oriented Programming.
- Modules and packages.
- Virtual environments.
- Basic asynchronous programming concepts.

## 4.2 FastAPI

**Category:** Python Backend Framework

Purpose: Build APIs that connect the Streamlit frontend with the AI processing system.

Responsibilities:

- Receive YouTube URLs.
- Validate incoming requests.
- Trigger transcript extraction.
- Manage video processing.
- Handle user queries.
- Manage chat sessions.
- Return AI-generated responses.
- Handle application errors.

Why FastAPI?

- Python-based framework.
- Automatic API documentation.
- Request validation through Pydantic.
- Supports asynchronous operations.
- Suitable for AI-powered backend services.

Knowledge Required:

- HTTP fundamentals.
- REST APIs.
- GET and POST requests.
- JSON.
- Request and response handling.
- API routing.
- Pydantic models.
- Exception handling.
- Basic asynchronous programming.

Official Documentation:

https://fastapi.tiangolo.com/

## 4.3 Uvicorn

**Category:** ASGI Server

Purpose: Run the FastAPI application.

Responsibilities:

- Start the backend server.
- Handle incoming HTTP requests.
- Serve the FastAPI application.

Knowledge Required:

- Basic server concepts.
- Running Python applications.
- Host and port configuration.

Official Documentation:

https://www.uvicorn.org/

---

# 5. RAG Framework

## 5.1 LangChain

**Category:** LLM Application Development Framework

Purpose: Simplify the development and orchestration of the RAG pipeline.

Responsibilities:

- Document loading integrations.
- Text splitting.
- Embedding integrations.
- Vector store integration.
- Retriever operations.
- Prompt templates.
- LLM integration.

Why LangChain?

It provides reusable abstractions for connecting different AI components.

It will help organize the RAG pipeline without manually implementing every integration.

Knowledge Required:

- Python functions and classes.
- Document objects.
- Text chunking.
- Embeddings.
- Vector databases.
- Retrieval.
- Prompt templates.
- LLM integration.

Important:

LangChain is an orchestration framework, not an LLM or a vector database.

Official Documentation:

https://python.langchain.com/docs/introduction/

---

# 6. YouTube Transcript Extraction

## 6.1 youtube-transcript-api

**Category:** Python Library

Purpose: Extract available transcripts from YouTube videos.

Responsibilities:

- Retrieve available transcripts.
- Extract transcript text.
- Preserve timestamps.
- Handle transcript language selection.
- Report transcript availability issues.

Why this library?

It provides a Python interface for accessing available YouTube transcript data without implementing a complete transcription engine.

Knowledge Required:

- Python package installation.
- Function calls.
- API-like response structures.
- Lists and dictionaries.
- Exception handling.
- JSON-like data processing.

Important Limitations:

- Not every video has an accessible transcript.
- Captions may be disabled.
- Access may be restricted.
- YouTube may change its access behavior.
- Availability and reliability must be tested.

This library is not equivalent to the official YouTube Data API.

---

# 7. Text Processing

## 7.1 LangChain Text Splitters

**Category:** Text Processing Library

Purpose: Divide long transcripts into smaller text chunks.

Responsibilities:

- Split long transcript text.
- Control chunk size.
- Maintain overlap between adjacent chunks.
- Preserve meaningful context.
- Prepare documents for embedding generation.

Important Concepts:

**Chunk Size:** Maximum approximate size of an individual text chunk.

**Chunk Overlap:** Shared text between consecutive chunks to reduce loss of context at boundaries.

Initial experimental configuration:

- Chunk size: 800 characters.
- Chunk overlap: 150 characters.

These values are starting points, not final performance guarantees. They will be evaluated using actual transcripts.

Knowledge Required:

- String manipulation.
- Lists.
- Text preprocessing.
- Document metadata.
- Chunking concepts.

---

# 8. Embedding Technologies

## 8.1 Hugging Face

**Category:** AI Model Ecosystem

Purpose: Access and use pre-trained embedding models.

Hugging Face provides access to various models for NLP and other AI tasks.

Official Website:

https://huggingface.co/

## 8.2 Sentence Transformers

**Category:** Python Embedding Library

Purpose: Convert transcript chunks and user queries into numerical vectors.

Selected Initial Model:

all-MiniLM-L6-v2

Model Characteristics:

- Sentence embedding model.
- Produces 384-dimensional embeddings.
- Suitable for semantic similarity tasks.
- Can run locally.
- Does not require a paid embedding API.

Responsibilities:

- Generate transcript chunk embeddings.
- Generate query embeddings.
- Convert text into vector representations.

Knowledge Required:

- Basic NLP.
- Word and sentence embeddings.
- Vector representations.
- Cosine similarity.
- Semantic similarity.
- Model loading and inference.

Model Reference:

https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2

---

# 9. Database Technologies

## 9.1 Supabase

**Category:** Backend-as-a-Service Platform

Purpose: Provide managed PostgreSQL database infrastructure.

TubeTalk AI will use Supabase for persistent application data.

Responsibilities:

- Store video metadata.
- Store chat sessions.
- Store conversation messages.
- Store transcript chunks.
- Support database queries.
- Support vector search through pgvector.

Official Website:

https://supabase.com/

## 9.2 PostgreSQL

**Category:** Relational Database Management System

Purpose: Manage structured application data.

Initial tables:

- videos
- chat_sessions
- chat_messages
- transcript_chunks

Knowledge Required:

- Database fundamentals.
- Tables and columns.
- Primary keys.
- Foreign keys.
- Relationships.
- SQL SELECT, INSERT, UPDATE, DELETE.
- Basic joins.
- Database constraints.

## 9.3 pgvector

**Category:** PostgreSQL Vector Extension

Purpose: Store and search vector embeddings inside PostgreSQL.

Responsibilities:

- Store embedding vectors.
- Perform similarity searches.
- Retrieve relevant transcript chunks.
- Filter results by video ID.

Knowledge Required:

- Vector embeddings.
- Vector similarity.
- Cosine distance.
- Basic SQL.
- Vector indexing fundamentals.

Important:

The initial embedding model produces 384-dimensional vectors. The database vector column must use the compatible dimension.

Documentation:

https://github.com/pgvector/pgvector

---

# 10. LLM Integration

## 10.1 Groq

**Category:** LLM Inference Platform

Purpose: Generate natural-language responses using hosted Large Language Models.

Responsibilities:

- Process retrieved transcript context.
- Generate contextual answers.
- Summarize video content.
- Generate key takeaways.
- Handle follow-up questions.

Why Groq?

- Fast inference.
- Developer-friendly API.
- Supports multiple instruction-following models.
- Provides options for initial experimentation.

Knowledge Required:

- LLM fundamentals.
- Prompt engineering.
- API integration.
- API keys.
- Request and response handling.
- Token limits.
- Temperature and generation parameters.
- Hallucination and grounding concepts.

Official Website:

https://groq.com/

Important:

Available models, context limits, pricing, and free-tier quotas may change. We will verify the currently supported model before implementation.

## 10.2 LangChain Groq Integration

**Category:** LangChain Integration Package

Purpose: Connect Groq-hosted LLMs with the LangChain application.

Responsibilities:

- Configure the Groq model.
- Send prompts.
- Receive generated responses.
- Integrate the LLM into the RAG pipeline.

---

# 11. Development and Version Control

## 11.1 Visual Studio Code

Purpose: Main development environment.

Responsibilities:

- Write Python code.
- Manage project files.
- Run the frontend and backend.
- Debug errors.
- Manage dependencies.

## 11.2 Git

Purpose: Track changes in the project codebase.

Knowledge Required:

- git init.
- git add.
- git commit.
- git status.
- git log.
- git branch.
- git push.
- git pull.

## 11.3 GitHub

Purpose: Host the project repository and maintain version history.

Responsibilities:

- Store source code.
- Maintain documentation.
- Track project progress.
- Manage development branches.
- Share the project publicly.

---

# 12. Deployment Technologies

## 12.1 Streamlit Community Cloud

Purpose: Deploy the Streamlit frontend.

Responsibilities:

- Host the user interface.
- Connect the application with the backend.
- Provide a public application URL.

Official Website:

https://streamlit.io/cloud

## 12.2 Render

Purpose: Deploy the FastAPI backend.

Responsibilities:

- Host the Python backend.
- Provide a public API endpoint.
- Handle incoming application requests.

Official Website:

https://render.com/

Deployment considerations:

- Environment variables.
- API URLs.
- Dependency installation.
- Server startup commands.
- CORS configuration.
- Service availability and hosting limits.

---

# 13. Proposed Python Dependencies

The following packages are expected to be used during implementation.

| Package | Purpose |
|---|---|
| streamlit | Frontend |
| fastapi | Backend API |
| uvicorn | Backend server |
| langchain | RAG orchestration |
| langchain-community | Community integrations |
| langchain-text-splitters | Text chunking |
| langchain-groq | Groq integration |
| youtube-transcript-api | Transcript extraction |
| sentence-transformers | Embeddings |
| supabase | Supabase client |
| python-dotenv | Environment variables |
| pydantic | Data validation |
| requests | HTTP communication |

Additional packages may be introduced only when a specific requirement justifies them.

Exact compatible versions will be determined and pinned during implementation.

---

# 14. Environment and Configuration

The project will use a Python virtual environment.

All dependencies will be maintained in a requirements.txt file.

Sensitive credentials will be stored in environment variables.

Expected configuration values:

- GROQ_API_KEY
- SUPABASE_URL
- SUPABASE_KEY

Production credentials must never be committed to GitHub.

The project will use separate development and production configurations wherever necessary.

---

# 15. Technology Learning Prerequisites

Before using a technology in TubeTalk AI, the following knowledge should be covered.

| Technology | Learning Requirements |
|---|---|
| Python | Fundamentals, functions, OOP, exceptions, modules |
| Streamlit | Layouts, widgets, session state |
| FastAPI | REST APIs, HTTP, routing, Pydantic |
| LangChain | Documents, splitters, retrievers, prompts |
| YouTube Transcript API | Package usage, transcript structures |
| Hugging Face | Models, embeddings, inference |
| Sentence Transformers | Semantic embeddings, similarity |
| PostgreSQL | SQL, tables, relationships |
| Supabase | Database connection and queries |
| pgvector | Vector storage and similarity search |
| Groq | LLM APIs, prompts, response handling |
| Git | Version control and GitHub workflow |

---

# 16. Alternative Technologies

The following technologies may be considered in future versions.

| Current Selection | Alternative |
|---|---|
| Streamlit | React |
| FastAPI | Flask |
| LangChain | LlamaIndex |
| Hugging Face | OpenAI Embeddings |
| Supabase pgvector | ChromaDB / Pinecone |
| Groq | Gemini / Mistral |
| Render | Railway / Other Cloud Hosting |

These alternatives are not part of the initial implementation plan.

---

# 17. Technology Selection Conclusion

TubeTalk AI will use a Python-centric technology stack.

Streamlit will provide the frontend, FastAPI will manage backend operations, and LangChain will orchestrate the RAG workflow.

Hugging Face will provide local embedding generation, Supabase pgvector will manage vector storage and semantic retrieval, and Groq will provide LLM inference.

The selected stack is intended to provide a practical balance between learning, development speed, cost, and future extensibility.

**TubeTalk AI — Don't Just Watch. Understand and Interact.**