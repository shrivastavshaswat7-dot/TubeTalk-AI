from dataclasses import dataclass, field


@dataclass(frozen=True)
class VideoMetadata:
    youtube_video_id: str
    youtube_url: str
    title: str | None = None
    channel_name: str | None = None
    thumbnail_url: str | None = None


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    start: float  # seconds
    duration: float  # seconds

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass(frozen=True)
class Transcript:
    youtube_video_id: str
    language_code: str
    is_generated: bool
    segments: list[TranscriptSegment] = field(default_factory=list)
