# M10 UI Implementation Brief (Streamlit)

**Audience:** the engineer/agent building the Streamlit frontend. **Backend is finished (M1–M9) and must not change.**
**Verified against:** the live OpenAPI schema of the backend at commit `4069e26`.
**Specs this implements:** `docs/08_UI_UX_Requirements.md` (within V1 scope), `docs/07_Chat_Memory_Sessions.md`.

---

## 1. Scope

**Build:** Home (submit a video, recent videos), Video Workspace (video info, chat, sessions), Insights view (summary, takeaways, topics), backend status, loading/error/empty states.

**Do NOT build:** authentication, user accounts, video deletion, session renaming, streaming responses, voice, playlists, multi-video chat, advanced retrieval controls, custom theme toggle, anything that needs a backend change. If something seems to need a backend change, list it in the PR notes instead of working around it.

**Rules that must hold everywhere**
1. The frontend holds **no secrets** and talks **only** to the backend through `frontend/api_client.py`. No Supabase/Groq/YouTube calls from the UI.
2. **Never use `unsafe_allow_html=True`** for anything from the API (titles, answers, sources are untrusted text). Plain Streamlit markdown/text only.
3. **Never invent content.** If the API says an answer is not grounded or a transcript is unavailable, show exactly that.
4. **Strict isolation in the UI:** every session call sends the current `video_id` with the `session_id`. Cache messages keyed by `(video_id, session_id)`. Switching video or session clears the chat view before loading the new one.
5. API base URL comes only from `config.get_api_base_url()` (env `API_BASE_URL` or Streamlit secrets). Keep existing `config.py` and `check_health()`.

---

## 2. Run and structure

```
backend (repo root, venv active):   cd backend ; python -m uvicorn app.main:app --port 8000
frontend:                           cd frontend ; python -m streamlit run app.py
```

Suggested layout (use the existing `pages/` and `components/` folders; keep `config.py`, `api_client.py`):

```
frontend/
  app.py                 # entry: page config, st.navigation([Home, Workspace]), shared sidebar
  api_client.py          # ONE function per endpoint + ApiError (see §4)
  config.py              # existing
  state.py               # session_state helpers + query-param sync
  pages/home.py          # Home / dashboard
  pages/workspace.py     # Video workspace (Chat | Insights)
  components/            # sidebar.py, video_card.py, chat.py, insights.py, sources.py, errors.py
  .streamlit/config.toml # base theme only (light/dark follows the user's Streamlit setting)
  requirements.txt       # keep minimal (streamlit, requests); add nothing heavy
```

Dependencies: `streamlit==1.66.1`, `requests` (already pinned). No new packages unless unavoidable.

---

## 3. Screens and flows

### 3.1 Sidebar (all pages)
- App name/tagline, **Home** link, **Backend status** (existing `check_health()`, with a Refresh button).
- **Recent videos**: from `GET /api/videos`; show only `processing_status == "completed"`, title truncated, click opens the Workspace.
- When a video is open: **Sessions for this video** (§3.4) and **New conversation** button.
- Footer: short "about" line. Theme = Streamlit's built-in Settings menu (no custom toggle).

### 3.2 Home
- Title, tagline, `st.text_input` for the YouTube URL, **Process video** button (disabled while empty or while processing).
- On submit: `POST /api/videos/process` inside `st.status("Processing video…")` with text such as "Fetching transcript, creating embeddings. This can take a minute or more for long videos." (the call is synchronous; no real progress is available, so use an indeterminate message).
- On success: if `reused` is true show a toast "Already processed, opened existing video"; navigate to the Workspace with `video.id` and `session.id` set.
- On error: show the mapped message (§6) in `st.error`, keep the URL in the input, stay on Home.
- **Recent videos** as cards (thumbnail, title, channel, language). Empty state: "No videos yet. Paste a YouTube link above to begin." Cards that are `failed` / `transcript_unavailable` are hidden from this list.

### 3.3 Workspace (requires an open video)
Header: thumbnail, title, channel, "Open on YouTube" link (`youtube_url`), processing status badge (text + icon, not color alone).
A view switch `st.segmented_control` (or `st.radio(horizontal=True)`): **Chat | Insights**. **Do not use `st.tabs`** for this: Streamlit runs every tab body on each rerun, which would trigger insight generation on every chat message.

**Video player:** an `st.expander("Watch video")` with `st.video(youtube_url, start_time=<int seconds>)`. Clicking a timestamp (§3.5) stores `player_start` in session state, opens the expander and reruns. Every timestamp also has an "Open on YouTube" link using `timestamp_url` (new tab).

If the video is not found / not completed (direct URL with a bad id): show the error and a button back to Home.

### 3.4 Sessions (per video)
- List = `GET /api/videos/{video_id}/sessions` (newest activity first). Label each as `"{session_title} · {relative/local created_at}"` (all titles default to "New Conversation", so the date/time is what distinguishes them).
- **New conversation:** `POST /api/sessions {video_id, session_title?}` then switch to it.
- **Switch:** set active session, load `GET /api/sessions/{session_id}/messages?video_id=…`.
- **Delete (current session):** `DELETE /api/sessions/{session_id}?video_id=…` behind an `st.dialog`/confirm. Deleting removes only the session and its messages, never the video. Afterwards switch to the most recent remaining session, or create a new one if none is left.
- Opening a video from Home/sidebar uses its most recent session (first in the list); processing returns a default session already.

### 3.5 Chat view
- Render history with `st.chat_message("user"|"assistant")`, chronological. Empty state: "Ask anything about this video. Answers come only from its transcript." with 3 non-clickable example questions or clickable starters that submit as a normal message.
- `st.chat_input("Ask about this video…", max_chars=2000)`. On submit: show the user bubble immediately, then an assistant bubble with `st.spinner("Thinking…")`, then call `POST /api/chat`, then render the answer. Block a second submit while one is pending.
- **Answer rendering**
  - `grounded == true`: answer text, then an `st.expander("Sources (n)")` listing each source: `[mm:ss – mm:ss]` chip as a button (seeks the player) + "Open on YouTube" (`timestamp_url`) + the excerpt (`content`, truncated, expandable). Sort sources by `start_time` for display; show similarity only as small caption text or omit.
  - `grounded == false`: show the answer text (it is the "couldn't find that in this video's transcript" message) in a visually distinct style (e.g. `st.info`) with **no** sources section.
  - Do not parse `[mm:ss]` out of the answer text; use `sources[]` for all links.
- Optional caption under an answer to a follow-up: "Searched as: *{standalone_question}*" when it differs from the user's message (helps transparency).
- History loaded from `GET …/messages` has the same shape; `messages[].sources` is `null` for user messages and a list (possibly empty) for assistant messages. Render restored sessions identically to live ones, including timestamp links.

### 3.6 Insights view
- Fetch **once per video**, store in `st.session_state[("insights", video_id)]`. Do not refetch on reruns.
- First view: show `st.spinner("Generating insights… this can take up to a minute for long videos")` while calling `GET /api/videos/{id}/insights` (first call generates; later calls are cached by the backend, `cached: true`).
- Sections: **Summary** (text), **Key takeaways** (bullet list), **Topics** (list: name + `[timestamp]` button → seeks player, + "Open on YouTube" link; if `timestamp` is `null` show the name only).
- Footer caption: "Generated {generated_at local} by {model}" and a **Regenerate** button (confirm first) → `POST /api/videos/{id}/insights/regenerate`; on failure keep showing the existing insights and show the error (the backend preserves them).
- `409 INSIGHTS_GENERATING`: show "Insights are being generated, please wait" with a **Check again** button (no auto-polling loop).
- Failure on first generation: error message + **Try again** button.
- Do not call `/summary`, `/takeaways`, `/topics` separately; `/insights` returns all three.

---

## 4. API client contract (`api_client.py`)

Base URL from `config.get_api_base_url()`. Every function returns the parsed JSON body on success; on any failure it raises one `ApiError(code, message, status)`:
- HTTP error: read `{"success": false, "error": CODE, "message": text}`; fall back to `code="HTTP_ERROR"` if the body isn't JSON.
- Network failure → `ApiError("BACKEND_UNREACHABLE", "Cannot reach the TubeTalk backend…")`; timeout → `ApiError("TIMEOUT", …)`.

| Function | Request | Timeout |
|---|---|---|
| `health()` | `GET /health` (keep existing `check_health`) | 5 s |
| `process_video(url)` | `POST /api/videos/process` `{"youtube_url"}` | **300 s** |
| `list_videos()` | `GET /api/videos` | 15 s |
| `get_video(video_id)` | `GET /api/videos/{video_id}` | 15 s |
| `list_sessions(video_id)` | `GET /api/videos/{video_id}/sessions` | 15 s |
| `create_session(video_id, title=None)` | `POST /api/sessions` `{"video_id","session_title"?}` → **201** | 15 s |
| `get_messages(session_id, video_id)` | `GET /api/sessions/{session_id}/messages?video_id=` | 15 s |
| `delete_session(session_id, video_id)` | `DELETE /api/sessions/{session_id}?video_id=` | 15 s |
| `chat(video_id, session_id, message)` | `POST /api/chat` | **90 s** |
| `get_insights(video_id)` | `GET /api/videos/{video_id}/insights` | **300 s** (first call generates) |
| `regenerate_insights(video_id)` | `POST /api/videos/{video_id}/insights/regenerate` | **300 s** |

(`GET /api/sessions/{id}?video_id=` exists but is not needed.) All IDs are UUID strings.

### Response shapes (exact field names)

```jsonc
// POST /api/videos/process -> 200
{ "success": true, "message": "...", "reused": false,
  "video":   { "id","youtube_video_id","youtube_url","title","channel_name","thumbnail_url",
               "transcript_language","processing_status","created_at" },   // nullable: title, channel_name, thumbnail_url, transcript_language
  "session": { "id","video_id","session_title","created_at","updated_at" } }

// POST /api/chat -> 200
{ "success": true, "session_id": "...", "answer": "...", "grounded": true,
  "standalone_question": "...",
  "sources": [ { "chunk_id","chunk_index","content","start_time","end_time","similarity","timestamp_url" } ],  // times are seconds (float|null)
  "user_message":      { "id","session_id","role":"user","content","sources":null,"created_at" },
  "assistant_message": { "id","session_id","role":"assistant","content","sources":[...],"created_at" } }

// GET /api/sessions/{id}/messages -> { "success": true, "messages": [ MessageOut, ... ] }   // chronological
// GET /api/videos -> { "success": true, "videos": [ VideoOut, ... ] }                        // up to 20, any status
// GET /api/videos/{id}/sessions -> { "success": true, "sessions": [ SessionOut, ... ] }       // newest activity first

// GET /api/videos/{id}/insights -> 200
{ "success": true, "video_id": "...", "cached": true,
  "insights": { "summary": "...", "key_takeaways": ["..."], 
                "topics": [ { "name","start_time","timestamp":"mm:ss"|null,"timestamp_url"|null } ],
                "model": "...", "generated_at": "ISO-8601" } }
```

Timestamps in `created_at`/`updated_at`/`generated_at` are ISO-8601 UTC strings: format them in the user's local time. `start_time`/`end_time` are seconds; format as `mm:ss` (or `h:mm:ss` over an hour).

---

## 5. State and session handling

- **Active video/session survive a browser refresh** via `st.query_params` (`?video=<uuid>&session=<uuid>`); on load, read them, validate with `get_video` / `get_messages` (bad ids → friendly error + Home). Streamlit's `session_state` alone is lost on refresh.
- `session_state` keys (suggested): `video`, `session_id`, `messages[(video_id, session_id)]`, `insights[video_id]`, `player_start`, `pending` (bool), `sessions[video_id]`.
- Refresh the sessions list only after a mutation (create/delete/first message) to avoid a backend call on every rerun. Refresh recent videos on Home load and after processing.
- Optimistic UI is fine for the user's own message; on a failed `chat` call, remove the optimistic bubble, show the error, and **restore the text so the user can resend** (nothing is saved by the backend when a chat call fails).
- One in-flight request at a time per page; disable submit controls while `pending`.

---

## 6. Error handling (map `ApiError.code` to user text; never show raw tracebacks or JSON)

| Code | Message to show |
|---|---|
| `BACKEND_UNREACHABLE` | "Can't reach the backend. Make sure it is running." (+ Retry) |
| `TIMEOUT` | "This is taking longer than expected. Please try again." |
| `INVALID_VIDEO_URL` | "Please enter a valid YouTube link." |
| `VIDEO_NOT_FOUND` | "That video doesn't exist or was removed." |
| `VIDEO_RESTRICTED` | "That video is private, age-restricted or unavailable." |
| `TRANSCRIPT_UNAVAILABLE` | Use the API `message` (captions disabled / none found / empty). Nothing can be asked about this video. |
| `UNSUPPORTED_LANGUAGE` | Use the API `message` (it lists available languages). V1 supports English transcripts only. |
| `YOUTUBE_BLOCKED`, `NETWORK_ERROR` | "YouTube couldn't be reached. Try again in a moment." |
| `VIDEO_PROCESSING` | "This video is already being processed. Please wait a moment and try again." |
| `PROCESSING_FAILED`, `EMBEDDING_ERROR` | "The video couldn't be processed. Please try again." |
| `VIDEO_NOT_READY` | "This video hasn't finished processing." |
| `SESSION_NOT_FOUND` | "That conversation no longer exists." → switch/create session |
| `SESSION_VIDEO_MISMATCH` | Treat as a bug: reload the workspace from Home (should never occur in normal use). |
| `EMPTY_MESSAGE` | "Please enter a question." |
| `LLM_RATE_LIMITED` (429) | "The AI service is busy. Wait a few seconds and try again." |
| `LLM_UNAVAILABLE`, `LLM_ERROR` | "The AI service had a problem. Please try again." |
| `LLM_NOT_CONFIGURED`, `DATABASE_NOT_CONFIGURED`, `DATABASE_ERROR`, `INTERNAL_ERROR` | "Something went wrong on our side. Please try again later." |
| `INSIGHTS_GENERATING` | see §3.6 |
| `INSIGHTS_FAILED` | "Couldn't generate insights for this video. Try again." |
| `VALIDATION_ERROR` (422) | "That input isn't valid." |
| anything else | the API `message` if present, else a generic message |

Errors use `st.error` (icon + text), never color alone. Keep prior content on screen when an action fails.

---

## 7. UX requirements checklist

- Loading feedback for every call over ~1 s (spinner/status). Long calls (process, first insights) state that they can take a while.
- Empty states: no videos, no sessions, empty chat, no topics.
- Chat is the primary area; video player collapsed by default.
- Readable on desktop and mobile: avoid more than two columns; stack on narrow screens; thumbnail + title header must not overflow.
- Accessibility: descriptive button labels, status shown as text, sufficient contrast (rely on Streamlit's themes), keyboard-usable controls.
- Light/dark: follow Streamlit's theme; define only a base in `.streamlit/config.toml`.
- Visual style: minimal and clean (docs/08 §10). No custom CSS beyond small spacing tweaks.

---

## 8. Acceptance tests

**Automated** (`streamlit.testing.v1.AppTest` with `api_client` functions monkeypatched; no real network): home renders; processing success navigates to workspace; each error code in §6 renders its message; chat success shows answer + sources; `grounded=false` shows no sources; failed chat restores input; session switch loads the right messages; messages cache is keyed by `(video_id, session_id)`; insights fetched once per video.

**Manual end-to-end (backend running, real services).** Suggested public videos: `jNQXAC9IVRw` ("Me at the zoo", 19 s) and `aircAruvnKk` (19 min lecture).
1. Paste an invalid link → friendly error. Paste a valid link → processing status → Workspace opens.
2. Paste the same link again → "already processed" toast, same video/session, no wait.
3. Ask a question → grounded answer with sources; click a timestamp → player seeks; "Open on YouTube" link opens at that time.
4. Ask a follow-up using "it"/"them" → answer is correct; caption shows the rewritten question.
5. Ask something unrelated → "couldn't find that" message, no sources.
6. New conversation → empty chat; switch back → old messages with source links restored.
7. Refresh the browser → same video and session reopen (query params).
8. Process a second video → its sessions/messages are completely separate; no content from video A appears.
9. Open Insights → spinner, then summary/takeaways/topics; reopen → instant (cached); Regenerate works.
10. Stop the backend → status shows unreachable and actions show the retry message; restart → recovers.
11. A video without English captions → clear error, no workspace.

**Definition of done:** all of the above pass; `pytest` in `backend/` still passes (backend untouched); no secrets or `.env` committed; frontend README section updated with run instructions.

---

## 9. Known backend behaviours to design around (no backend change needed)

- Processing and first-time insights are **synchronous and can take minutes** for long videos; use the long timeouts and the status messages above.
- Session titles are all "New Conversation" by default; distinguish sessions by date/time.
- `GET /api/videos` returns all statuses (failed videos included) and is **global** (V1 is single-user; no auth). Filter to `completed` in the UI.
- `sources` are ordered by similarity, not time; sort by `start_time` when displaying.
- Chat sends no streaming; the full answer arrives at once.
- There is no endpoint to delete videos or rename sessions in V1.
- Chat answers may be refused (`grounded: false`) even for plausible questions when the transcript does not contain the answer; that is correct behaviour.
