from __future__ import annotations

import wave
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import NoReturn, Protocol, cast

import av
from av.audio.resampler import AudioResampler
from PIL import Image


class MediaProcessingError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        blocked: bool = False,
        result: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.blocked = blocked
        self.result = result or {}


@dataclass(frozen=True)
class MediaStreamInfo:
    stream_index: int
    stream_type: str
    codec_name: str
    duration_ms: int | None
    frame_count: int | None
    width: int | None = None
    height: int | None = None
    sample_rate: int | None = None
    channels: int | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "stream_index": self.stream_index,
            "stream_type": self.stream_type,
            "codec_name": self.codec_name,
            "duration_ms": self.duration_ms,
            "frame_count": self.frame_count,
            "width": self.width,
            "height": self.height,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
        }


@dataclass(frozen=True)
class PreparedMediaArtifact:
    artifact_id: str
    role: str
    media_type: str
    path: Path
    content_hash: str
    byte_size: int
    timestamp_ms: int | None = None
    frame_index: int | None = None

    def public_metadata(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "role": self.role,
            "media_type": self.media_type,
            "content_hash": self.content_hash,
            "byte_size": self.byte_size,
            "timestamp_ms": self.timestamp_ms,
            "frame_index": self.frame_index,
        }


@dataclass(frozen=True)
class PreparedMedia:
    source_path: Path
    format_name: str
    duration_ms: int
    streams: tuple[MediaStreamInfo, ...]
    artifacts: tuple[PreparedMediaArtifact, ...]

    @property
    def audio_artifact(self) -> PreparedMediaArtifact | None:
        return next(
            (artifact for artifact in self.artifacts if artifact.role == "audio_track"),
            None,
        )

    @property
    def frame_artifacts(self) -> tuple[PreparedMediaArtifact, ...]:
        return tuple(artifact for artifact in self.artifacts if artifact.role == "video_frame")

    def public_manifest(self) -> dict[str, object]:
        return {
            "format_name": self.format_name,
            "duration_ms": self.duration_ms,
            "streams": [stream.as_dict() for stream in self.streams],
            "artifacts": [artifact.public_metadata() for artifact in self.artifacts],
        }


@dataclass(frozen=True)
class MediaTranscriptSegment:
    text: str
    timestamp_start_ms: int
    timestamp_end_ms: int
    confidence: float
    media_artifact_id: str = "audio_track"


@dataclass(frozen=True)
class MediaFrameObservation:
    text: str
    media_artifact_id: str
    confidence: float


@dataclass(frozen=True)
class MediaUnderstandingResult:
    connector_id: str
    connector_version: str
    model_id: str
    transcript_segments: tuple[MediaTranscriptSegment, ...] = ()
    frame_observations: tuple[MediaFrameObservation, ...] = ()


class MediaUnderstandingConnector(Protocol):
    @property
    def connector_id(self) -> str: ...

    @property
    def connector_version(self) -> str: ...

    @property
    def model_id(self) -> str: ...

    async def analyze(self, prepared: PreparedMedia) -> MediaUnderstandingResult: ...


@dataclass(frozen=True)
class MediaDerivedFragment:
    text: str
    kind: str
    media_artifact: PreparedMediaArtifact
    confidence: float
    timestamp_start_ms: int
    timestamp_end_ms: int | None = None


def validate_media_understanding(
    prepared: PreparedMedia,
    result: MediaUnderstandingResult,
    *,
    max_fragments: int,
    max_text_chars: int,
) -> tuple[MediaDerivedFragment, ...]:
    artifacts = {artifact.artifact_id: artifact for artifact in prepared.artifacts}
    fragments: list[MediaDerivedFragment] = []
    for segment in result.transcript_segments:
        artifact = artifacts.get(segment.media_artifact_id)
        if artifact is None or artifact.role != "audio_track":
            _invalid_understanding("A transcript referenced an unknown audio artifact.")
        _validate_text_and_confidence(segment.text, segment.confidence, max_text_chars)
        if (
            segment.timestamp_start_ms < 0
            or segment.timestamp_end_ms <= segment.timestamp_start_ms
            or segment.timestamp_end_ms > prepared.duration_ms
        ):
            _invalid_understanding("A transcript timestamp was outside the source duration.")
        fragments.append(
            MediaDerivedFragment(
                text=segment.text,
                kind="media_time",
                media_artifact=artifact,
                confidence=segment.confidence,
                timestamp_start_ms=segment.timestamp_start_ms,
                timestamp_end_ms=segment.timestamp_end_ms,
            )
        )
    for observation in result.frame_observations:
        artifact = artifacts.get(observation.media_artifact_id)
        if artifact is None or artifact.role != "video_frame":
            _invalid_understanding("A frame observation referenced an unknown frame artifact.")
        _validate_text_and_confidence(observation.text, observation.confidence, max_text_chars)
        if artifact.timestamp_ms is None:
            _invalid_understanding("A frame observation referenced a frame without a timestamp.")
        fragments.append(
            MediaDerivedFragment(
                text=observation.text,
                kind="media_frame",
                media_artifact=artifact,
                confidence=observation.confidence,
                timestamp_start_ms=artifact.timestamp_ms,
            )
        )
    if not fragments:
        raise MediaProcessingError(
            "MEDIA_UNDERSTANDING_EMPTY",
            "The media connector returned no transcript or frame observations.",
        )
    if len(fragments) > max_fragments:
        raise MediaProcessingError(
            "MEDIA_FRAGMENT_LIMIT_EXCEEDED",
            "The media connector returned more fragments than the configured safe limit.",
            blocked=True,
        )
    return tuple(fragments)


def _validate_text_and_confidence(text: str, confidence: float, max_text_chars: int) -> None:
    if not text or text != text.strip() or len(text) > max_text_chars:
        _invalid_understanding("A media-derived text fragment was empty or invalid.")
    if not 0 <= confidence <= 1:
        _invalid_understanding("A media-derived confidence value was invalid.")


def _invalid_understanding(message: str) -> NoReturn:
    raise MediaProcessingError("MEDIA_UNDERSTANDING_INVALID", message)


class PyAvMediaProcessor:
    """Performs bounded local decoding; it never opens a URL or invokes a model."""

    def __init__(
        self,
        *,
        max_duration_seconds: float,
        max_streams: int,
        frame_interval_seconds: float,
        max_frames: int,
        max_frame_dimension: int,
        max_decoded_video_frames: int,
        audio_sample_rate: int,
        max_audio_bytes: int,
    ) -> None:
        self.max_duration_ms = int(max_duration_seconds * 1000)
        self.max_streams = max_streams
        self.frame_interval_ms = max(1, int(frame_interval_seconds * 1000))
        self.max_frames = max_frames
        self.max_frame_dimension = max_frame_dimension
        self.max_decoded_video_frames = max_decoded_video_frames
        self.audio_sample_rate = audio_sample_rate
        self.max_audio_bytes = max_audio_bytes

    def prepare(self, source_path: Path, output_directory: Path) -> PreparedMedia:
        output_directory.mkdir(parents=True, exist_ok=False)
        try:
            with av.open(str(source_path), mode="r") as container:
                streams = tuple(self._stream_info(stream) for stream in container.streams)
                duration_ms = self._duration_ms(container, streams)
                format_name = container.format.name or "unknown"
        except (av.error.FFmpegError, OSError, ValueError) as exc:
            raise MediaProcessingError(
                "MEDIA_CONTAINER_INVALID",
                "The uploaded media container is invalid or unsupported.",
            ) from exc

        if not streams or not any(stream.stream_type in {"audio", "video"} for stream in streams):
            raise MediaProcessingError(
                "MEDIA_STREAM_MISSING",
                "The media file does not contain a usable audio or video stream.",
                blocked=True,
            )
        if len(streams) > self.max_streams:
            raise MediaProcessingError(
                "MEDIA_STREAM_LIMIT_EXCEEDED",
                "The media file contains more streams than the configured safe limit.",
                blocked=True,
            )
        if duration_ms <= 0:
            raise MediaProcessingError(
                "MEDIA_DURATION_INVALID",
                "The media duration could not be established safely.",
                blocked=True,
            )
        if duration_ms > self.max_duration_ms:
            raise MediaProcessingError(
                "MEDIA_DURATION_LIMIT_EXCEEDED",
                "The media duration exceeds the configured safe limit.",
                blocked=True,
                result={"duration_ms": duration_ms},
            )

        artifacts: list[PreparedMediaArtifact] = []
        if any(stream.stream_type == "audio" for stream in streams):
            artifacts.append(self._extract_audio(source_path, output_directory))
        if any(stream.stream_type == "video" for stream in streams):
            artifacts.extend(self._extract_frames(source_path, output_directory))
        if not artifacts:
            raise MediaProcessingError(
                "MEDIA_EXTRACTION_EMPTY",
                "The media file did not produce an auditable audio track or video frame.",
                blocked=True,
            )
        return PreparedMedia(
            source_path=source_path,
            format_name=format_name,
            duration_ms=duration_ms,
            streams=streams,
            artifacts=tuple(artifacts),
        )

    def _extract_audio(self, source_path: Path, output_directory: Path) -> PreparedMediaArtifact:
        destination = output_directory / "audio_track.wav"
        written_pcm_bytes = 0
        try:
            with av.open(str(source_path), mode="r") as container:
                audio_stream = next(
                    stream for stream in container.streams if stream.type == "audio"
                )
                resampler = AudioResampler(format="s16", layout="mono", rate=self.audio_sample_rate)
                with wave.open(str(destination), "wb") as output:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(self.audio_sample_rate)
                    for decoded in container.decode(audio_stream):
                        frame = cast(av.AudioFrame, decoded)
                        for converted in resampler.resample(frame):
                            written_pcm_bytes = self._write_audio_frame(
                                output, converted, written_pcm_bytes
                            )
                    for converted in resampler.resample(None):
                        written_pcm_bytes = self._write_audio_frame(
                            output, converted, written_pcm_bytes
                        )
        except MediaProcessingError:
            raise
        except (av.error.FFmpegError, OSError, StopIteration, ValueError) as exc:
            raise MediaProcessingError(
                "MEDIA_AUDIO_DECODE_FAILED",
                "The media audio stream could not be decoded safely.",
            ) from exc
        if written_pcm_bytes == 0:
            raise MediaProcessingError(
                "MEDIA_AUDIO_EMPTY",
                "The decoded audio stream was empty.",
                blocked=True,
            )
        return self._artifact(
            artifact_id="audio_track",
            role="audio_track",
            media_type="audio/wav",
            path=destination,
        )

    def _write_audio_frame(
        self, output: wave.Wave_write, frame: av.AudioFrame, written: int
    ) -> int:
        payload = bytes(frame.planes[0])[: frame.samples * 2]
        total = written + len(payload)
        if total > self.max_audio_bytes:
            raise MediaProcessingError(
                "MEDIA_AUDIO_SIZE_LIMIT_EXCEEDED",
                "The normalized audio track exceeds the configured safe limit.",
                blocked=True,
            )
        output.writeframesraw(payload)
        return total

    def _extract_frames(
        self, source_path: Path, output_directory: Path
    ) -> list[PreparedMediaArtifact]:
        artifacts: list[PreparedMediaArtifact] = []
        next_timestamp_ms = 0
        decoded_frames = 0
        try:
            with av.open(str(source_path), mode="r") as container:
                video_stream = next(
                    stream for stream in container.streams if stream.type == "video"
                )
                for decoded in container.decode(video_stream):
                    frame = cast(av.VideoFrame, decoded)
                    decoded_frames += 1
                    if decoded_frames > self.max_decoded_video_frames:
                        raise MediaProcessingError(
                            "MEDIA_DECODED_FRAME_LIMIT_EXCEEDED",
                            "The video exceeded the configured decoded-frame limit.",
                            blocked=True,
                        )
                    timestamp_ms = self._frame_timestamp_ms(frame)
                    if timestamp_ms < next_timestamp_ms:
                        continue
                    frame_index = len(artifacts)
                    destination = output_directory / f"frame_{frame_index:04d}.png"
                    image = frame.to_image()  # type: ignore[no-untyped-call]
                    image.thumbnail(
                        (self.max_frame_dimension, self.max_frame_dimension),
                        Image.Resampling.LANCZOS,
                    )
                    image.save(destination, format="PNG", optimize=True)
                    artifacts.append(
                        self._artifact(
                            artifact_id=f"frame_{frame_index:04d}",
                            role="video_frame",
                            media_type="image/png",
                            path=destination,
                            timestamp_ms=timestamp_ms,
                            frame_index=frame_index,
                        )
                    )
                    next_timestamp_ms = timestamp_ms + self.frame_interval_ms
                    if len(artifacts) >= self.max_frames:
                        break
        except MediaProcessingError:
            raise
        except (av.error.FFmpegError, OSError, StopIteration, ValueError) as exc:
            raise MediaProcessingError(
                "MEDIA_VIDEO_DECODE_FAILED",
                "The media video stream could not be decoded safely.",
            ) from exc
        if not artifacts:
            raise MediaProcessingError(
                "MEDIA_VIDEO_EMPTY",
                "The decoded video stream did not contain a usable frame.",
                blocked=True,
            )
        return artifacts

    @staticmethod
    def _frame_timestamp_ms(frame: av.VideoFrame) -> int:
        if frame.time is not None:
            return max(0, int(frame.time * 1000))
        if frame.pts is not None and frame.time_base is not None:
            return max(0, int(frame.pts * frame.time_base * 1000))
        return 0

    @staticmethod
    def _stream_info(stream: av.stream.Stream) -> MediaStreamInfo:
        duration_ms: int | None = None
        if stream.duration is not None and stream.time_base is not None:
            duration_ms = max(0, int(stream.duration * stream.time_base * 1000))
        codec_context = stream.codec_context
        return MediaStreamInfo(
            stream_index=stream.index,
            stream_type=stream.type,
            codec_name=codec_context.name or "unknown",
            duration_ms=duration_ms,
            frame_count=stream.frames or None,
            width=getattr(codec_context, "width", None) or None,
            height=getattr(codec_context, "height", None) or None,
            sample_rate=getattr(codec_context, "sample_rate", None) or None,
            channels=getattr(codec_context, "channels", None) or None,
        )

    @staticmethod
    def _duration_ms(
        container: av.container.InputContainer,
        streams: tuple[MediaStreamInfo, ...],
    ) -> int:
        if container.duration is not None:
            return max(0, int(container.duration / 1000))
        durations = [stream.duration_ms for stream in streams if stream.duration_ms is not None]
        return max(durations, default=0)

    @staticmethod
    def _artifact(
        *,
        artifact_id: str,
        role: str,
        media_type: str,
        path: Path,
        timestamp_ms: int | None = None,
        frame_index: int | None = None,
    ) -> PreparedMediaArtifact:
        payload = path.read_bytes()
        return PreparedMediaArtifact(
            artifact_id=artifact_id,
            role=role,
            media_type=media_type,
            path=path,
            content_hash=sha256(payload).hexdigest(),
            byte_size=len(payload),
            timestamp_ms=timestamp_ms,
            frame_index=frame_index,
        )
