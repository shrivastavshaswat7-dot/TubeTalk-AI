# API Documentation

**Project Name:** TubeTalk AI  
**Document Type:** API Documentation  
**Version:** 1.0  
**Status:** Proposed  
**Backend Framework:** FastAPI  
**Frontend:** Streamlit  
**Communication Protocol:** HTTP / REST API  
**Data Format:** JSON

---

# 1. Introduction

## 1.1 Purpose

This document defines the REST API endpoints required for communication between the TubeTalk AI frontend and backend.

It specifies:

- API endpoints.
- HTTP methods.
- Request parameters.
- Request body structures.
- Response structures.
- Error handling.
- API validation rules.

## 1.2 API Architecture

The frontend will communicate with the backend using HTTP requests.

The backend will handle application logic, database operations, transcript processing, RAG retrieval, and LLM integration.

The frontend will display the results returned by the backend.

## 1.3 Base URL

Development:

```text
http://localhost:8000
```

Production:

```text
https://your-backend-domain.com
```

The production URL will be updated after deployment.

---

# 2. API Endpoint Overview

The initial application will contain the following endpoints.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | / | Backend health message |
| GET | /health | Health check |
| POST | /api/videos/process | Process YouTube video |
| GET | /api/videos/{video_id} | Retrieve video details |
| GET | /api/videos/{video_id}/sessions | Retrieve video sessions |
| POST | /api/sessions | Create a chat session |
| GET | /api/sessions/{session_id} | Retrieve session details |
| GET | /api/sessions/{session_id}/messages | Retrieve conversation history |
| POST | /api/chat | Send a message and receive an AI response |
| DELETE | /api/sessions/{session_id} | Delete a chat session |

---

# 3. Health Check APIs

## 3.1 Root Endpoint

**Endpoint:**

```http
GET /
```

Purpose:

Check whether the backend application is running.

Expected Response:

```json
{
  "message": "TubeTalk AI Backend is running"
}
```

## 3.2 Health Endpoint

**Endpoint:**

```http
GET /health
```

Purpose:

Check backend service health.

Expected Response:

```json
{
  "status": "healthy",
  "application": "TubeTalk AI"
}
```

---

# 4. Video Processing API

## 4.1 Process YouTube Video

**Endpoint:**

```http
POST /api/videos/process
```

Purpose:

Accept a YouTube URL and process the video transcript.

Responsibilities:

1. Validate the YouTube URL.
2. Extract the YouTube video ID.
3. Retrieve video metadata.
4. Extract available transcript.
5. Clean transcript text.
6. Divide transcript into chunks.
7. Generate embeddings.
8. Store video information.
9. Store transcript chunks and embeddings.
10. Create a default chat session.
11. Return processing information.

### Request Body

```json
{
  "youtube_url": "https://www.youtube.com/watch?v=example123"
}
```

### Successful Response

HTTP Status: `200 OK`

```json
{
  "success": true,
  "message": "Video processed successfully",
  "video": {
    "id": "video-uuid",
    "youtube_video_id": "example123",
    "title": "Introduction to Machine Learning",
    "thumbnail_url": "https://example.com/thumbnail.jpg",
    "processing_status": "completed"
  },
  "session": {
    "id": "session-uuid",
    "session_title": "New Conversation"
  }
}
```

### Error Responses

Invalid URL:

```json
{
  "success": false,
  "error": "INVALID_VIDEO_URL",
  "message": "Please provide a valid YouTube URL."
}
```

Transcript unavailable:

```json
{
  "success": false,
  "error": "TRANSCRIPT_UNAVAILABLE",
  "message": "No accessible transcript was found for this video."
}
```

Processing failure:

```json
{
  "success": false,
  "error": "PROCESSING_FAILED",
  "message": "The video could not be processed. Please try again."
}
```

### Important Implementation Note

Video processing may take time.

For the initial version, the endpoint may process the video synchronously and return the result after completion.

If processing time becomes excessive, a background job system can be introduced in a future version.

---

# 5. Video Information API

## 5.1 Get Video Details

**Endpoint:**

```http
GET /api/videos/{video_id}
```

Purpose:

Retrieve stored information about a processed video.

### Example Request

```http
GET /api/videos/12345
```

### Successful Response

```json
{
  "success": true,
  "video": {
    "id": "video-uuid",
    "title": "Introduction to Machine Learning",
    "youtube_video_id": "example123",
    "channel_name": "Example Channel",
    "processing_status": "completed"
  }
}
```

Possible errors:

- VIDEO_NOT_FOUND
- INVALID_VIDEO_ID

---

# 6. Chat Session APIs

## 6.1 Create Chat Session

**Endpoint:**

```http
POST /api/sessions
```

Purpose:

Create a new independent chat session for an existing video.

### Request Body

```json
{
  "video_id": "video-uuid",
  "session_title": "New Conversation"
}
```

### Successful Response

```json
{
  "success": true,
  "session": {
    "id": "session-uuid",
    "video_id": "video-uuid",
    "session_title": "New Conversation"
  }
}
```

## 6.2 Get Video Sessions

**Endpoint:**

```http
GET /api/videos/{video_id}/sessions
```

Purpose:

Retrieve all chat sessions associated with a particular video.

### Successful Response

```json
{
  "success": true,
  "sessions": [
    {
      "id": "session-001",
      "session_title": "Main Discussion"
    },
    {
      "id": "session-002",
      "session_title": "Exam Preparation"
    }
  ]
}
```

## 6.3 Get Session Details

**Endpoint:**

```http
GET /api/sessions/{session_id}
```

Purpose:

Retrieve information about an existing chat session.

### Successful Response

```json
{
  "success": true,
  "session": {
    "id": "session-uuid",
    "video_id": "video-uuid",
    "session_title": "Main Discussion"
  }
}
```

## 6.4 Delete Session

**Endpoint:**

```http
DELETE /api/sessions/{session_id}
```

Purpose:

Delete a chat session and its associated messages.

Expected Response:

```json
{
  "success": true,
  "message": "Session deleted successfully"
}
```

Important:

Deleting a session must not automatically delete the associated video or transcript chunks.

---

# 7. Chat History API

## 7.1 Retrieve Session Messages

**Endpoint:**

```http
GET /api/sessions/{session_id}/messages
```

Purpose:

Retrieve all messages associated with a chat session.

### Successful Response

```json
{
  "success": true,
  "messages": [
    {
      "id": "message-001",
      "role": "user",
      "content": "What is machine learning?",
      "created_at": "2026-11-07T10:00:00Z"
    },
    {
      "id": "message-002",
      "role": "assistant",
      "content": "Machine learning is a branch of AI...",
      "created_at": "2026-11-07T10:00:05Z"
    }
  ]
}
```

Messages must be returned in chronological order.

---

# 8. Chat API

## 8.1 Send Message

**Endpoint:**

```http
POST /api/chat
```

Purpose:

Accept a user question, retrieve relevant transcript chunks, use conversation history, and generate an AI response.

### Request Body

```json
{
  "video_id": "video-uuid",
  "session_id": "session-uuid",
  "message": "Explain the applications of machine learning."
}
```

### Backend Responsibilities

1. Validate the request.
2. Verify that the session belongs to the specified video.
3. Retrieve relevant session history.
4. Understand whether the question is a follow-up.
5. Contextualize the query when necessary.
6. Generate a query embedding.
7. Retrieve relevant transcript chunks using video-specific filtering.
8. Construct the LLM prompt.
9. Send the prompt to Groq.
10. Receive the generated answer.
11. Save the user message.
12. Save the assistant response.
13. Return the response and source references.

### Successful Response

```json
{
  "success": true,
  "session_id": "session-uuid",
  "answer": "Machine learning is used in healthcare, finance, recommendation systems, and many other fields.",
  "sources": [
    {
      "chunk_id": "chunk-001",
      "start_time": 125.5,
      "end_time": 180.0,
      "content": "Machine learning has applications in healthcare..."
    }
  ]
}
```

### Error Responses

Empty message:

```json
{
  "success": false,
  "error": "EMPTY_MESSAGE",
  "message": "Please enter a question."
}
```

Invalid session:

```json
{
  "success": false,
  "error": "SESSION_NOT_FOUND",
  "message": "The requested chat session does not exist."
}
```

Session-video mismatch:

```json
{
  "success": false,
  "error": "SESSION_VIDEO_MISMATCH",
  "message": "The session does not belong to the requested video."
}
```

LLM failure:

```json
{
  "success": false,
  "error": "LLM_ERROR",
  "message": "Unable to generate a response at the moment."
}
```

---

# 9. Response Generation Rules

The chat API must follow these rules:

1. Answers must be grounded in retrieved transcript context.
2. The assistant must not invent information that is absent from the transcript.
3. Relevant timestamps should be included when available.
4. Follow-up questions should use the active session history.
5. Retrieval must remain restricted to the active video.
6. If sufficient transcript context is unavailable, the assistant should clearly communicate the limitation.
7. Conversation history must be saved persistently.

---

# 10. HTTP Status Codes

| Status Code | Meaning |
|---|---|
| 200 | Successful request |
| 201 | Resource created |
| 400 | Invalid request |
| 404 | Resource not found |
| 422 | Request validation failed |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
| 503 | External service unavailable |

The implementation should use suitable status codes instead of returning HTTP 200 for every error.

---

# 11. API Security

Initial security requirements:

- API keys must remain on the backend.
- Validate all incoming requests.
- Use parameterized database queries.
- Configure CORS for the frontend origin.
- Avoid exposing internal error details.
- Protect privileged database operations.
- Apply rate limits where necessary.

Future versions may introduce authentication and user-specific authorization.

---

# 12. API Validation

The backend must validate:

- YouTube URL format.
- Video ID format.
- Session ID.
- Video and session relationship.
- Message length.
- Empty input.
- Required request fields.
- Unsupported requests.

Validation should be implemented using Pydantic models and appropriate backend logic.

---

# 13. API Documentation Interface

FastAPI provides automatic interactive API documentation.

Development URL:

```text
http://localhost:8000/docs
```

Alternative documentation:

```text
http://localhost:8000/redoc
```

These interfaces will help test API endpoints during development.

---

# 14. Future API Enhancements

Possible future endpoints:

- POST /api/videos/{video_id}/summary
- GET /api/videos/{video_id}/key-takeaways
- POST /api/videos/{video_id}/quiz
- POST /api/videos/{video_id}/reprocess
- PATCH /api/sessions/{session_id}
- POST /api/feedback

These are not required for the initial API implementation.

---

# 15. Conclusion

The TubeTalk AI API layer will use FastAPI to connect the Streamlit frontend with the backend processing system.

The endpoints will manage video processing, session management, chat history, and contextual question answering.

The API design prioritizes clear communication, request validation, error handling, and strict video-session isolation.

**TubeTalk AI — Don't Just Watch. Understand and Interact.**