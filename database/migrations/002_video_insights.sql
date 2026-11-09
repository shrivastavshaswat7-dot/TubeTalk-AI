-- TubeTalk AI: cached video insights (summary, key takeaways, topics).
-- Run once in the Supabase SQL editor, after 001_init.sql.

create table if not exists video_insights (
    video_id       uuid primary key references videos(id) on delete cascade,
    status         varchar(20) not null default 'generating'
        check (status in ('generating', 'completed', 'failed')),
    summary        text,
    key_takeaways  jsonb,   -- ["...", "..."]
    topics         jsonb,   -- [{"name": "...", "start_time": 123.0}, ...]
    model          text,    -- LLM that produced the insights
    error_message  text,    -- last failure; completed rows may keep one after a failed regeneration
    generated_at   timestamptz,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);

drop trigger if exists trg_video_insights_updated_at on video_insights;
create trigger trg_video_insights_updated_at before update on video_insights
    for each row execute function set_updated_at();

-- Same as the other tables: RLS on, no policies; the backend's service-role key bypasses it.
alter table video_insights enable row level security;
