-- TubeTalk AI: give the records created before sign-in existed to their owner. Run once in the
-- Supabase SQL editor, after 003 and after the owner has signed in with Google at least once.
--
-- Set the owner's Google email in the one line marked below. Everything runs in one transaction and
-- stops without changing anything unless exactly one signed-in user has that email.
--
-- What it changes (nothing is deleted):
--   * user_videos:          adds the owner's library: every completed video, plus any video that
--                           already has a conversation
--   * chat_sessions:        sets user_id = owner on sessions that have no owner yet (user_id is null);
--                           sessions that already have an owner are not touched. The updated_at
--                           trigger is paused, so conversations keep their dates and order.
--   * user_video_insights:  copies the existing shared insights into the owner's own rows
--                           (existing rows are left as they are)
-- The legacy video_insights table, videos, transcript chunks and messages are not modified.

begin;

alter table chat_sessions disable trigger trg_chat_sessions_updated_at;

do $$
declare
    owner_email constant text := 'OWNER_GOOGLE_EMAIL';  -- <== the owner's Google sign-in email
    owner_id uuid;
    matches int;
    added_videos int;
    claimed_sessions int;
    copied_insights int;
begin
    if owner_email = 'OWNER_GOOGLE_EMAIL' then
        raise exception 'Set owner_email first.';
    end if;
    select count(*) into matches from auth.users where lower(email) = lower(owner_email);
    if matches <> 1 then
        raise exception 'Expected exactly one signed-in user with that email, found %.', matches;
    end if;
    select id into owner_id from auth.users where lower(email) = lower(owner_email);

    insert into user_videos (user_id, video_id, created_at)
    select owner_id, v.id, v.created_at
    from videos v
    where v.processing_status = 'completed'
       or exists (select 1 from chat_sessions s where s.video_id = v.id and s.user_id is null)
    on conflict (user_id, video_id) do nothing;
    get diagnostics added_videos = row_count;

    update chat_sessions set user_id = owner_id where user_id is null;
    get diagnostics claimed_sessions = row_count;

    insert into user_video_insights (user_id, video_id, status, summary, key_takeaways, topics, model,
                                     error_message, generated_at, created_at, updated_at)
    select owner_id, vi.video_id, vi.status, vi.summary, vi.key_takeaways, vi.topics, vi.model,
           vi.error_message, vi.generated_at, vi.created_at, vi.updated_at
    from video_insights vi
    on conflict (user_id, video_id) do nothing;
    get diagnostics copied_insights = row_count;

    raise notice 'Backfill: % library rows added, % sessions assigned, % insights copied.',
        added_videos, claimed_sessions, copied_insights;
end $$;

alter table chat_sessions enable trigger trg_chat_sessions_updated_at;

commit;
