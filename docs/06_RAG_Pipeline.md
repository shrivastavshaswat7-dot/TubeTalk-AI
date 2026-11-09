# TubeTalk AI
# RAG Pipeline Design

**Version:** 1.0  
**Status:** Proposed  
**Architecture:** Retrieval-Augmented Generation (RAG)

## 1. Introduction

### 1.1 Purpose

This document defines the complete RAG pipeline responsible for understanding YouTube video transcripts and answering user questions.

TubeTalk AI will use Basic Retrieval-Augmented Generation (RAG).

The system will retrieve relevant transcript information before generating an answer through an LLM.

### 1.2 What is RAG?

Retrieval-Augmented Generation combines two operations:

1. Retrieval: Finding relevant information from an external knowledge source.
2. Generation: Using an LLM to generate an answer based on the retrieved information.

Instead of relying entirely on the LLM's internal knowledge, TubeTalk AI will use the actual video transcript as its primary knowledge source.

## 2. RAG Architecture

The system consists of two main pipelines:

- Document Ingestion Pipeline
- User Query Pipeline

## 3. Document Ingestion Pipeline

### Step 1: YouTube URL Input

The user submits a YouTube URL.

The backend validates the URL and extracts the video ID.

### Step 2: Video Metadata Extraction

The application retrieves available metadata, such as:

- Video title
- Channel name
- Thumbnail
- Video ID

### Step 3: Transcript Extraction

The YouTube Transcript API retrieves available captions.

The application preserves:

- Transcript text
- Starting timestamp
- Ending timestamp
- Language information

If no accessible transcript exists, processing stops with a meaningful error.

### Step 4: Transcript Cleaning

Remove unnecessary formatting and normalize transcript text.

Examples:

- Remove empty segments.
- Normalize whitespace.
- Handle repeated text.
- Preserve meaningful punctuation where possible.

Timestamps must remain associated with their corresponding transcript content.

### Step 5: Text Chunking

Divide the transcript into smaller segments.

Initial experimental configuration:

- Chunk size: 800 characters.
- Chunk overlap: 150 characters.

These values will be evaluated and adjusted during testing.

Each chunk should retain metadata:

- video_id
- chunk_index
- start_time
- end_time
- content

### Step 6: Embedding Generation

Convert every transcript chunk into a numerical vector.

Initial model:

all-MiniLM-L6-v2

Embedding dimension:

384

### Step 7: Vector Storage

Store transcript chunks and their embeddings in Supabase PostgreSQL using pgvector.

The ingestion pipeline is now complete.

## 4. User Query Pipeline

### Step 1: Receive User Question

The frontend sends:

- video_id
- session_id
- user message

### Step 2: Retrieve Conversation History

Retrieve previous messages belonging only to the active session.

### Step 3: Query Contextualization

Determine whether the question depends on earlier conversation.

Example:

Previous question:
"What is supervised learning?"

Follow-up:
"What are its applications?"

The system can contextualize the follow-up as:

"What are the applications of supervised learning?"

This contextualized question is used for retrieval.

### Step 4: Query Embedding

Convert the contextualized question into a vector using the same embedding model used during ingestion.

### Step 5: Semantic Retrieval

Search the vector database for transcript chunks similar to the query.

Retrieval must be filtered by the active video ID.

Initial retrieval configuration:

Top K = 5 chunks.

This value will be evaluated experimentally.

### Step 6: Prompt Construction

Construct a prompt containing:

- System instructions
- Relevant transcript chunks
- Conversation context
- Current user question

### Step 7: LLM Generation

Send the constructed prompt to the selected Groq model.

The LLM generates an answer grounded in retrieved transcript information.

### Step 8: Save Conversation

Save:

- User message
- Assistant response

Both messages must belong to the active session.

### Step 9: Return Response

Return:

- Generated answer
- Relevant timestamps
- Source references

## 5. Prompt Design Requirements

The system prompt must instruct the LLM to:

1. Answer using the supplied transcript context.
2. Avoid inventing unsupported information.
3. Clearly communicate when information is unavailable.
4. Use conversation history to understand follow-up questions.
5. Include relevant timestamps when available.
6. Avoid treating unrelated external knowledge as video content.

## 6. Retrieval Configuration

Initial parameters:

| Parameter | Initial Value |
|---|---|
| Embedding Model | all-MiniLM-L6-v2 |
| Embedding Dimension | 384 |
| Chunk Size | 800 characters |
| Chunk Overlap | 150 characters |
| Top K | 5 |
| Retrieval Method | Semantic Similarity |
| Database | Supabase pgvector |

These are experimental starting values, not permanent constraints.

## 7. Timestamp Handling

Every transcript chunk must preserve its original time range.

The application should generate timestamp links using the video's ID and the relevant starting time.

Example:

https://www.youtube.com/watch?v=VIDEO_ID&t=275s

This link should open the video near the relevant section.

## 8. Error Handling

The RAG pipeline must handle:

- Transcript unavailable.
- Empty transcript.
- Embedding generation failure.
- Database connection failure.
- No relevant retrieval results.
- LLM API failure.
- Context exceeding model limits.

The application must not generate misleading transcript-based answers when retrieval fails.

## 9. Evaluation Criteria

The RAG pipeline will be evaluated using:

- Retrieval relevance.
- Answer correctness.
- Contextual accuracy.
- Timestamp accuracy.
- Hallucination rate.
- Response latency.

## 10. Future Enhancements

Not included in version 1.0:

- Hybrid search.
- Reranking.
- Query expansion.
- Multi-query retrieval.
- Advanced metadata filtering.
- Audio-based understanding.
- Video frame analysis.

## 11. Conclusion

TubeTalk AI will use a Basic RAG pipeline consisting of transcript extraction, preprocessing, chunking, embedding generation, semantic retrieval, prompt construction, and LLM generation.

The initial goal is to build a reliable and understandable RAG system before introducing advanced retrieval techniques.

**TubeTalk AI — Don't Just Watch. Understand and Interact.**