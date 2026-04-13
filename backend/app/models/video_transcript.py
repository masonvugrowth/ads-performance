"""Video transcript model — stores transcriptions and AI analysis for video ads."""

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin, UUIDType


class VideoTranscript(TimestampMixin, Base):
    __tablename__ = "video_transcripts"

    # Link to material (video) — optional if processing from raw ad URL
    material_id = Column(
        UUIDType,
        ForeignKey("ad_materials.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    combo_id = Column(
        UUIDType,
        ForeignKey("ad_combos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Source
    video_url = Column(Text, nullable=False)
    language = Column(String(10), nullable=True)  # detected language: en, vi, zh, ja

    # Transcription result
    transcript = Column(Text, nullable=True)

    # AI analysis from Claude
    ai_analysis = Column(JSON, nullable=True)
    # Structure:
    # {
    #   "summary": "Brief summary of the video content",
    #   "suggested_angle_type": "one of the 13 angle types",
    #   "suggested_angle_explain": "Why this angle works for this ad",
    #   "suggested_hook_examples": ["hook line 1", "hook line 2"],
    #   "suggested_keypoints": [
    #     {"category": "location|amenity|experience|value", "title": "keypoint text"},
    #   ],
    #   "detected_ta": "Solo|Couple|Family|Group|null",
    #   "tone": "emotional|informational|urgency|aspirational|etc",
    # }

    # Processing status
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    # PENDING → TRANSCRIBING → ANALYZING → COMPLETED / FAILED
    error_message = Column(Text, nullable=True)
    processing_time_seconds = Column(Float, nullable=True)

    # Who triggered it
    triggered_by = Column(String(100), nullable=True)  # user email or "system"
