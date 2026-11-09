# TubeTalk AI
# Chat Memory & Session Management

**Version:** 1.0  
**Status:** Proposed

## 1. Introduction

This document defines how TubeTalk AI manages conversation history, contextual memory, and independent chat sessions.

The purpose is to maintain meaningful conversations without mixing information between different videos or sessions.

## 2. Memory Architecture

TubeTalk AI will use two separate information mechanisms:

### 2.1 Conversation Memory

Stores previous user and assistant messages.

Purpose:

- Understand follow-up questions.
- Maintain conversational context.
- Resolve references such as "it", "that topic", and "its applications".
- Restore previous conversations.

### 2.2 RAG Knowledge Retrieval

Retrieves factual information from the transcript stored in the vector database.

Purpose:

- Find relevant transcript information.
- Ground generated answers in video content.
- Provide timestamp references.

Important distinction:

Conversation memory helps understand what the user means.

RAG retrieval helps identify what the video actually says.

Neither should replace the other.

## 3. Session Management

Every chat session will have:

- Unique session ID.
- Associated video ID.
- Session title.
- Creation timestamp.
- Last activity timestamp.

A video may have multiple sessions.

Every newly processed video should automatically receive a default session.

## 4. Session Isolation

Session isolation is a critical requirement.

Example:

Video A:
- Session 1: General discussion
- Session 2: Exam preparation

Video B:
- Session 3: General discussion

Rules:

- Session 1 must never retrieve Session 2 history.
- Video B must never retrieve Video A transcript chunks.
- Every session must reference its correct video.
- Active session and active video relationships must be validated.

## 5. Follow-up Question Handling

Example conversation:

User:
"What is deep learning?"

Assistant:
"Deep learning is a subset of machine learning..."

User:
"What are its applications?"

The system should understand that "its" refers to deep learning.

Proposed process:

1. Fetch recent conversation history.
2. Identify contextual references.
3. Rewrite the follow-up as a standalone question.
4. Retrieve relevant transcript chunks.
5. Generate a grounded answer.
6. Save the new messages.

## 6. Persistent Chat History

All messages must be stored in PostgreSQL.

When a user reopens a session:

1. Fetch session information.
2. Fetch its messages.
3. Display the conversation chronologically.
4. Continue using the same session context.

Conversation history must not disappear when the browser or application is refreshed.

## 7. Context Window Management

The entire conversation should not be sent to the LLM indefinitely.

The system should use a controlled amount of recent history.

Initial approach:

- Fetch recent messages.
- Use relevant conversation context.
- Contextualize the current question.
- Retrieve transcript chunks.
- Keep the final prompt within model token limits.

Advanced summarization of long conversation history may be introduced later.

## 8. Session Titles

New sessions may initially use the default title:

"New Conversation"

A future enhancement may generate titles based on the first meaningful user question.

## 9. Memory Failure Handling

The system must handle:

- Missing session history.
- Deleted sessions.
- Invalid session IDs.
- Session-video mismatch.
- Database retrieval errors.
- Excessively long conversation history.

The application must never silently substitute another session's history.

## 10. Future Enhancements

- Conversation summarization.
- User preferences.
- Saved important answers.
- Session search.
- Session renaming.
- Export conversation.
- Cross-session search, only when explicitly requested and safely scoped.

## 11. Conclusion

TubeTalk AI will use persistent, session-specific conversation history combined with transcript-based RAG retrieval.

This architecture will support natural follow-up conversations while maintaining strict separation between videos and sessions.

**TubeTalk AI — Don't Just Watch. Understand and Interact.**