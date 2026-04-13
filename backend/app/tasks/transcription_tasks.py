"""Celery tasks for video transcription and AI classification."""

import logging
import time

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models.video_transcript import VideoTranscript
from app.models.ad_material import AdMaterial
from app.models.ad_combo import AdCombo
from app.models.account import AdAccount

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def transcribe_and_classify_task(self, transcript_id: str):
    """Async task: transcribe video → classify with Claude.

    Updates VideoTranscript row through each stage:
    PENDING → TRANSCRIBING → ANALYZING → COMPLETED / FAILED
    """
    db = SessionLocal()
    try:
        record = db.query(VideoTranscript).filter(VideoTranscript.id == transcript_id).first()
        if not record:
            logger.error("VideoTranscript %s not found", transcript_id)
            return {"error": "Record not found"}

        start_time = time.time()

        # --- Stage 1: Transcribe ---
        record.status = "TRANSCRIBING"
        db.commit()

        from app.services.transcription_service import transcribe_video

        try:
            result = transcribe_video(record.video_url)
        except Exception as e:
            record.status = "FAILED"
            record.error_message = f"Transcription failed: {e}"
            record.processing_time_seconds = time.time() - start_time
            db.commit()
            logger.error("Transcription failed for %s: %s", transcript_id, e)
            return {"error": str(e)}

        record.transcript = result["transcript"]
        record.language = result["language"]

        if not result["transcript"] or len(result["transcript"].strip()) < 10:
            record.status = "COMPLETED"
            record.error_message = "No speech detected in video"
            record.processing_time_seconds = time.time() - start_time
            record.ai_analysis = {"summary": "No speech detected", "suggested_keypoints": []}
            db.commit()
            return {"status": "completed", "warning": "no speech detected"}

        # --- Stage 2: Classify with Claude ---
        record.status = "ANALYZING"
        db.commit()

        from app.services.ai_classifier import classify_transcript

        # Resolve branch name for context
        branch_name = "Unknown"
        if record.material_id:
            mat = db.query(AdMaterial).filter(AdMaterial.id == record.material_id).first()
            if mat:
                acc = db.query(AdAccount).filter(AdAccount.id == mat.branch_id).first()
                if acc:
                    branch_name = acc.account_name
        elif record.combo_id:
            combo = db.query(AdCombo).filter(AdCombo.id == record.combo_id).first()
            if combo:
                acc = db.query(AdAccount).filter(AdAccount.id == combo.branch_id).first()
                if acc:
                    branch_name = acc.account_name

        try:
            analysis = classify_transcript(
                transcript=result["transcript"],
                branch_name=branch_name,
                language=result["language"],
            )
        except Exception as e:
            # Classification failed but transcription succeeded
            record.status = "COMPLETED"
            record.error_message = f"AI classification failed: {e}"
            record.processing_time_seconds = time.time() - start_time
            db.commit()
            logger.warning("AI classification failed for %s: %s", transcript_id, e)
            return {"status": "completed", "warning": f"classification failed: {e}"}

        record.ai_analysis = analysis
        record.status = "COMPLETED"
        record.processing_time_seconds = time.time() - start_time
        db.commit()

        logger.info(
            "Transcribe+classify complete for %s: angle=%s, %d keypoints, %.1fs total",
            transcript_id,
            analysis.get("suggested_angle_type", "?"),
            len(analysis.get("suggested_keypoints", [])),
            record.processing_time_seconds,
        )

        return {
            "status": "completed",
            "transcript_length": len(result["transcript"]),
            "language": result["language"],
            "angle_type": analysis.get("suggested_angle_type"),
            "keypoints_count": len(analysis.get("suggested_keypoints", [])),
        }

    except Exception as e:
        logger.exception("Unexpected error in transcribe_and_classify_task")
        try:
            record = db.query(VideoTranscript).filter(VideoTranscript.id == transcript_id).first()
            if record:
                record.status = "FAILED"
                record.error_message = f"Unexpected error: {e}"
                db.commit()
        except Exception:
            pass
        raise self.retry(exc=e)
    finally:
        db.close()
