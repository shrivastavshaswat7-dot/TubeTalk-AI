# TubeTalk AI
# Technical Architecture Document (TAD)

**Project Name:** TubeTalk AI  
**Document Type:** Technical Architecture Document  
**Version:** 1.0  
**Status:** Proposed Architecture  
**Architecture Style:** Modular Client-Server Architecture  
**Core Architecture:** Retrieval-Augmented Generation (RAG)

---

# 1. Introduction

## 1.1 Purpose

This document defines the technical architecture of TubeTalk AI.

It describes the system components, their responsibilities, communication flow, data processing pipeline, and interactions between different modules.

The document will serve as the technical blueprint for implementation.

## 1.2 Architectural Overview

TubeTalk AI will follow a modular architecture consisting of:

1. Frontend Layer
2. Backend Layer
3. Transcript Processing Layer
4. Embedding Generation Layer
5. Vector Storage Layer
6. Retrieval Layer
7. LLM Generation Layer
8. Chat Memory and Session Management Layer

The architecture will separate video processing from question-answering operations.

---

# 2. High-Level System Architecture

The system will contain two primary workflows:

### A. Video Ingestion Pipeline

Responsible for converting YouTube video transcripts into searchable vector representations.

Workflow:

YouTube URL → Transcript Extraction → Text Cleaning → Chunking → Embedding Generation → Vector Storage.

### B. Query Processing Pipeline

Responsible for understanding user questions and generating answers using retrieved transcript information.

Workflow:

User Query → Session Identification → Conversation Context → Query Processing → Semantic Retrieval → Prompt Construction → LLM → Response.

---

# 3. System Components

## 3.1 Frontend Layer

**Technology:** Streamlit

Responsibilities:

- Provide the main application interface.
- Accept YouTube video URLs.
- Display video information.
- Display video previews wherever supported.
- Provide an interactive chat interface.
- Display AI-generated answers.
- Display summaries and key takeaways.
- Display relevant timestamps.
- Allow users to access previous chat sessions.

The frontend will communicate with the backend through HTTP APIs.

## 3.2 Backend Layer

**Technology:** Python + FastAPI

Responsibilities:

- Handle frontend API requests.
- Validate YouTube URLs.
- Coordinate transcript extraction.
- Trigger the RAG ingestion pipeline.
- Manage chat sessions.
- Retrieve conversation history.
- Execute query processing.
- Communicate with the LLM.
- Store and retrieve application data.
- Handle application errors.

The backend will act as the central orchestration layer.

## 3.3 Transcript Extraction Layer

**Technology:** YouTube Transcript API

Responsibilities:

- Extract available video transcripts.
- Retrieve transcript text.
- Preserve timestamp metadata.
- Identify unavailable transcripts.
- Handle extraction failures.

The initial system will depend on accessible YouTube captions or transcripts.

## 3.4 Text Processing Layer

**Technology:** LangChain Text Splitters

Responsibilities:

- Clean extracted transcript text.
- Remove unnecessary formatting.
- Divide transcripts into smaller chunks.
- Maintain chunk ordering.
- Preserve timestamp metadata.
- Prepare chunks for embedding generation.

Each chunk will retain its relationship with the original video.

## 3.5 Embedding Generation Layer

**Technology:** Hugging Face Sentence Transformers

Proposed initial model:

all-MiniLM-L6-v2

Responsibilities:

- Convert transcript chunks into numerical vector representations.
- Generate query embeddings.
- Maintain a compatible embedding space for documents and queries.

The same embedding model must be used for both transcript chunks and user queries.

