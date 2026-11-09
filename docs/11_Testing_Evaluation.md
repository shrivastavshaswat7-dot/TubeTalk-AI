# TubeTalk AI
# Testing and Evaluation Plan

**Version:** 1.0  
**Status:** Proposed

## 1. Introduction

This document defines the testing strategy for TubeTalk AI.

The objective is to verify that individual components and the complete application work correctly.

Testing will focus on functionality, reliability, retrieval quality, answer accuracy, and performance.

## 2. Testing Objectives

- Verify functional requirements.
- Identify bugs.
- Validate API responses.
- Test database relationships.
- Evaluate retrieval relevance.
- Evaluate answer grounding.
- Verify session isolation.
- Test failure scenarios.
- Measure application performance.

## 3. Testing Types

### 3.1 Unit Testing

Tests individual modules independently.

Examples:

- URL validation.
- Video ID extraction.
- Transcript cleaning.
- Text chunking.
- Embedding generation.
- Timestamp conversion.

Proposed Tool: pytest

### 3.2 API Testing

Tests FastAPI endpoints.

Examples:

- Health check.
- Video processing.
- Session creation.
- Chat requests.
- Message retrieval.
- Invalid request handling.

Tools:

- FastAPI TestClient.
- Swagger UI.
- pytest.

### 3.3 Database Testing

Verifies:

- Table creation.
- Foreign keys.
- Record insertion.
- Record retrieval.
- Session relationships.
- Vector storage.
- Video filtering.

### 3.4 Integration Testing

Tests multiple components working together.

Example:

YouTube URL → Transcript → Chunks → Embeddings → Database.

Another example:

Question → Retrieval → Prompt → LLM → Response.

### 3.5 End-to-End Testing

Tests the complete user workflow.

Example:

1. Open application.
2. Submit YouTube URL.
3. Process video.
4. Ask a question.
5. Receive an answer.
6. Ask a follow-up question.
7. Close and reopen the session.
8. Verify conversation history.

## 4. Functional Test Cases

| ID | Test Case | Expected Result |
|---|---|---|
| TC-01 | Valid YouTube URL | URL accepted |
| TC-02 | Invalid URL | Validation error |
| TC-03 | Accessible transcript | Transcript extracted |
| TC-04 | Unavailable transcript | Clear error displayed |
| TC-05 | Transcript chunking | Chunks generated |
| TC-06 | Embedding generation | 384-dimensional vectors |
| TC-07 | Vector storage | Embeddings stored |
| TC-08 | Relevant question | Relevant chunks retrieved |
| TC-09 | Chat response | Answer generated |
| TC-10 | Follow-up question | Context maintained |
| TC-11 | Session reopening | History restored |
| TC-12 | Different video | Correct video context used |
| TC-13 | Timestamp reference | Correct video section opens |
| TC-14 | LLM failure | Error handled |
| TC-15 | Empty message | Request rejected |

## 5. RAG Evaluation

RAG quality must be evaluated separately from general application functionality.

### 5.1 Retrieval Evaluation

Measure:

- Relevance of retrieved chunks.
- Whether important information is retrieved.
- Whether results belong to the correct video.

Possible metrics:

- Precision@K.
- Recall@K.
- Mean Reciprocal Rank.

### 5.2 Answer Evaluation

Measure:

- Correctness.
- Relevance.
- Faithfulness to retrieved context.
- Completeness.
- Timestamp accuracy.

### 5.3 Hallucination Testing

Ask questions whose answers do not appear in the transcript.

Expected behavior:

The assistant should clearly state that the information is not available in the video transcript rather than inventing an answer.

## 6. Session Isolation Testing

This is a critical test category.

Scenario:

- Process Video A.
- Ask several questions.
- Process Video B.
- Ask unrelated questions.
- Return to Video A.
- Reopen an earlier session.

Expected results:

- Video A retrieves only Video A transcript chunks.
- Video B retrieves only Video B transcript chunks.
- Each session restores its own conversation history.
- No messages appear in unrelated sessions.

## 7. Error Testing

Test the following conditions:

- Invalid YouTube URL.
- Deleted video.
- Private video.
- Restricted transcript.
- Unsupported language.
- Empty transcript.
- Network interruption.
- Database failure.
- Invalid API key.
- LLM rate limit.
- LLM timeout.
- Invalid session ID.

## 8. Performance Testing

Measure:

- Transcript processing duration.
- Embedding generation duration.
- Database retrieval duration.
- LLM response duration.
- Complete response latency.

Performance expectations will be established using representative test videos rather than arbitrary guarantees.

## 9. Test Dataset

Prepare a small dataset of publicly accessible videos covering different topics.

Suggested categories:

- Programming.
- Artificial Intelligence.
- Education.
- Technology.
- General knowledge.

For each video, create questions with known answers and relevant transcript timestamps.

Include questions that are intentionally unanswerable from the transcript.

## 10. Regression Testing

Whenever an existing module changes, previously working features must be tested again.

Particular attention should be given to:

- Session isolation.
- Transcript storage.
- Retrieval filters.
- Chat history.
- API communication.

## 11. Test Reporting

Maintain a test report containing:

- Test case ID.
- Test description.
- Expected result.
- Actual result.
- Pass or fail.
- Error details.
- Fix applied.

## 12. Acceptance Criteria

The initial release must:

- Pass critical functional tests.
- Handle expected failure scenarios.
- Maintain session isolation.
- Retrieve relevant transcript context.
- Generate grounded responses.
- Preserve conversation history.
- Work through the deployed frontend and backend.

## 13. Conclusion

Testing will be performed throughout development rather than only at the end.

The objective is to build a reliable AI application whose behavior can be demonstrated, evaluated, and explained.

**TubeTalk AI — Don't Just Build. Verify.**