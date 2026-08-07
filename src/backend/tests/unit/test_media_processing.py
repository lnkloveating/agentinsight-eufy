import math
import struct
import wave
from hashlib import sha256
from pathlib import Path

import av
import pytest
from PIL import Image

from app.sources.media_processing import (
    MediaFrameObservation,
    MediaProcessingError,
    MediaTranscriptSegment,
    MediaUnderstandingResult,
    PyAvMediaProcessor,
    validate_media_understanding,
)


def _wav_bytes(path: Path, *, duration_seconds: float = 1.0) -> bytes:
    sample_rate = 8_000
    sample_count = int(sample_rate * duration_seconds)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        for index in range(sample_count):
            sample = int(8_000 * math.sin(2 * math.pi * 440 * index / sample_rate))
            output.writeframesraw(struct.pack("<h", sample))
    return path.read_bytes()


def _video_file(path: Path) -> None:
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("mpeg4", rate=2)
        stream.width = 64
        stream.height = 48
        stream.pix_fmt = "yuv420p"
        for index, color in enumerate(("red", "green", "blue", "white")):
            image = Image.new("RGB", (64, 48), color=color)
            frame = av.VideoFrame.from_image(image)  # type: ignore[no-untyped-call]
            frame.pts = index
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def _processor(**overrides: object) -> PyAvMediaProcessor:
    values: dict[str, object] = {
        "max_duration_seconds": 10,
        "max_streams": 4,
        "frame_interval_seconds": 0.5,
        "max_frames": 10,
        "max_frame_dimension": 128,
        "max_decoded_video_frames": 100,
        "audio_sample_rate": 16_000,
        "max_audio_bytes": 1_000_000,
    }
    values.update(overrides)
    return PyAvMediaProcessor(**values)  # type: ignore[arg-type]


def test_audio_is_redecoded_to_bounded_mono_wav(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    _wav_bytes(source)

    prepared = _processor().prepare(source, tmp_path / "prepared")

    assert 990 <= prepared.duration_ms <= 1_010
    assert prepared.audio_artifact is not None
    artifact = prepared.audio_artifact
    assert artifact.media_type == "audio/wav"
    assert artifact.content_hash == sha256(artifact.path.read_bytes()).hexdigest()
    with wave.open(str(artifact.path), "rb") as decoded:
        assert decoded.getnchannels() == 1
        assert decoded.getframerate() == 16_000
        assert decoded.getsampwidth() == 2


def test_video_produces_bounded_timestamped_png_frames(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    _video_file(source)

    prepared = _processor().prepare(source, tmp_path / "prepared")

    assert prepared.audio_artifact is None
    assert len(prepared.frame_artifacts) >= 2
    assert [item.frame_index for item in prepared.frame_artifacts] == list(
        range(len(prepared.frame_artifacts))
    )
    assert [item.timestamp_ms for item in prepared.frame_artifacts] == sorted(
        item.timestamp_ms for item in prepared.frame_artifacts
    )
    for artifact in prepared.frame_artifacts:
        with Image.open(artifact.path) as image:
            assert image.format == "PNG"
            assert max(image.size) <= 128


def test_invalid_or_overlong_media_is_classified(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.mp4"
    invalid.write_bytes(b"not a media container")
    with pytest.raises(MediaProcessingError) as invalid_error:
        _processor().prepare(invalid, tmp_path / "invalid-output")
    assert invalid_error.value.code == "MEDIA_CONTAINER_INVALID"

    source = tmp_path / "long.wav"
    _wav_bytes(source, duration_seconds=1.0)
    with pytest.raises(MediaProcessingError) as duration_error:
        _processor(max_duration_seconds=0.5).prepare(
            source, tmp_path / "long-output"
        )
    assert duration_error.value.code == "MEDIA_DURATION_LIMIT_EXCEEDED"
    assert duration_error.value.blocked is True


def test_media_understanding_is_bound_to_real_artifacts_and_timestamps(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.wav"
    _wav_bytes(source)
    prepared = _processor().prepare(source, tmp_path / "prepared")
    valid = MediaUnderstandingResult(
        connector_id="test-asr",
        connector_version="1.0",
        model_id="test-model",
        transcript_segments=(
            MediaTranscriptSegment(
                text="A package was delivered.",
                timestamp_start_ms=0,
                timestamp_end_ms=900,
                confidence=0.91,
            ),
        ),
    )

    fragments = validate_media_understanding(
        prepared, valid, max_fragments=10, max_text_chars=1_000
    )

    assert fragments[0].media_artifact.content_hash == (
        prepared.audio_artifact.content_hash
    )
    assert fragments[0].timestamp_end_ms == 900

    invalid = MediaUnderstandingResult(
        connector_id="test-asr",
        connector_version="1.0",
        model_id="test-model",
        transcript_segments=(
            MediaTranscriptSegment(
                text="Invented out-of-range text.",
                timestamp_start_ms=0,
                timestamp_end_ms=2_000,
                confidence=0.5,
            ),
        ),
        frame_observations=(
            MediaFrameObservation(
                text="Unknown frame.",
                media_artifact_id="missing-frame",
                confidence=0.5,
            ),
        ),
    )
    with pytest.raises(MediaProcessingError) as error:
        validate_media_understanding(
            prepared, invalid, max_fragments=10, max_text_chars=1_000
        )
    assert error.value.code == "MEDIA_UNDERSTANDING_INVALID"
