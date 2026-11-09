-- TubeTalk AI: initial schema. Run once in the Supabase SQL editor.
-- V1 is single-user: one shared video record per YouTube video.
-- Before any public multi-user deployment, add user ownership + RLS policies.

create extension if not exists vector;

-- ---------------------------------------------------------------- videos
create table if not exists videos (
    id                  uuid primary key default gen_random_uuid(),
    youtube_video_id    varchar(20) not null unique,
    youtube_url         text not null,
    title               text,
    thumbnail_url       text,
    channel_name        text,
    transcript_language varchar(20),
    processing_status   varchar(30) not null default 'pending'
        check (processing_status in
            ('pending', 'processing', 'completed', 'failed', 'transcript_unavailable')),
    error_message       text,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

-- --------------------------------------------------------- chat_sessions
create table if not exists chat_sessions (
    id            uuid primary key default gen_random_uuid(),
    video_id      uuid not null references videos(id) on delete cascade,
    session_title text,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);
create index if not exists idx_chat_sessions_video_id on chat_sessions(video_id);

-- --------------------------------------------------------- chat_messages
create table if not exists chat_messages (
    id         uuid primary key default gen_random_uuid(),
    session_id uuid not null references chat_sessions(id) on delete cascade,
    role       varchar(20) not null check (role in ('user', 'assistant')),
    content    text not null check (length(btrim(content)) > 0),
    sources    jsonb,  -- retrieved chunks + timestamps, persisted with assistant answers
    created_at timestamptz not null default now()
);
create index if not exists idx_chat_messages_session_created
    on chat_messages(session_id, created_at);

-- ------------------------------------------------------ transcript_chunks
create table if not exists transcript_chunks (
    id          uuid primary key default gen_random_uuid(),
    video_id    uuid not null references videos(id) on delete cascade,
    chunk_index integer not null check (chunk_index >= 0),
    content     text not null,
    start_time  double precision check (start_time >= 0),
    end_time    double precision,
    embedding   vector(384),  -- all-MiniLM-L6-v2; change if the model changes
    created_at  timestamptz not null default now(),
    unique (video_id, chunk_index),
    check (end_time is null or start_time is null or end_time >= start_time)
);
create index if not exists idx_transcript_chunks_video_id on transcript_chunks(video_id);
-- Exact search is fine for a prototype; add an HNSW index later if needed:
-- create index on transcript_chunks using hnsw (embedding vector_cosine_ops);

-- ------------------------------------------------------- updated_at triggers
create or replace function set_updated_at() returns trigger
language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end $$;

drop trigger if exists trg_videos_updated_at on videos;
create trigger trg_videos_updated_at before update on videos
    for each row execute function set_updated_at();

drop trigger if exists trg_chat_sessions_updated_at on chat_sessions;
create trigger trg_chat_sessions_updated_at before update on chat_sessions
    for each row execute function set_updated_at();

-- A new message counts as session activity.
create or replace function touch_session_on_message() returns trigger
language plpgsql as $$
begin
    update chat_sessions set updated_at = now() where id = new.session_id;
    return new;
end $$;

drop trigger if exists trg_chat_messages_touch_session on chat_messages;
create trigger trg_chat_messages_touch_session after insert on chat_messages
    for each row execute function touch_session_on_message();

-- ------------------------------------------------------------ RLS
-- Enabled with NO policies: the anon/authenticated roles get no access.
-- The backend uses the service-role key, which bypasses RLS.
alter table videos            enable row level security;
alter table chat_sessions     enable row level security;
alter table chat_messages     enable row level security;
alter table transcript_chunks enable row level security;

-- ------------------------------------------------- similarity search (RPC)
-- Video isolation is enforced here: p_video_id is required and always filters.
create or replace function match_transcript_chunks(
    p_video_id      uuid,
    query_embedding vector(384),
    match_count     int default 5
)
returns table (
    id          uuid,
    chunk_index integer,
    content     text,
    start_time  double precision,
    end_time    double precision,
    similarity  double precision
)
language sql stable as $$
    select c.id, c.chunk_index, c.content, c.start_time, c.end_time,
           1 - (c.embedding <=> query_embedding) as similarity
    from transcript_chunks c
    where c.video_id = p_video_id
      and c.embedding is not null
    order by c.embedding <=> query_embedding
    limit match_count;
$$;

-- Not callable by public roles; backend (service role) only.
revoke all on function match_transcript_chunks(uuid, vector, int) from public, anon, authenticated;
