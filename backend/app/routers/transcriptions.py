"""Transcription endpoints — video transcription + AI classification."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.video_transcript import VideoTranscript
from app.models.ad_material import AdMaterial
from app.models.ad_combo import AdCombo

router = APIRouter()


def _api_response(data=None, error=None):
    return {
        "success": error is None,
        "data": data,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


class TranscribeRequest(BaseModel):
    video_url: str
    material_id: str | None = None
    combo_id: str | None = None


class TranscribeBatchRequest(BaseModel):
    """Batch transcribe multiple videos."""
    items: list[TranscribeRequest]


# ──────────────────────────────────────────────
# POST /api/transcribe — Start transcription
# ──────────────────────────────────────────────
@router.post("/transcribe")
def start_transcription(
    req: TranscribeRequest,
    db: Session = Depends(get_db),
):
    """Start async video transcription + AI classification.

    Queues a Celery task. Returns transcript_id to poll status.
    """
    try:
        # Create record
        record = VideoTranscript(
            id=str(uuid.uuid4()),
            video_url=req.video_url,
            material_id=req.material_id,
            combo_id=req.combo_id,
            status="PENDING",
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        # Queue Celery task
        from app.tasks.transcription_tasks import transcribe_and_classify_task
        transcribe_and_classify_task.delay(record.id)

        return _api_response(data={
            "transcript_id": record.id,
            "status": "PENDING",
            "message": "Transcription queued. Poll /api/transcripts/{id} for status.",
        })
    except Exception as e:
        return _api_response(error=str(e))


# ──────────────────────────────────────────────
# POST /api/transcribe/sync — Synchronous transcription (no Celery needed)
# ──────────────────────────────────────────────
@router.post("/transcribe/sync")
def sync_transcription(
    req: TranscribeRequest,
    db: Session = Depends(get_db),
):
    """Synchronous transcription — blocks until done.

    Use this if Celery/Redis is not running.
    WARNING: Can take 30-120 seconds depending on video length.
    """
    try:
        import time

        # Create record
        record = VideoTranscript(
            id=str(uuid.uuid4()),
            video_url=req.video_url,
            material_id=req.material_id,
            combo_id=req.combo_id,
            status="TRANSCRIBING",
        )
        db.add(record)
        db.commit()

        start_time = time.time()

        # Step 1: Transcribe
        from app.services.transcription_service import transcribe_video
        result = transcribe_video(req.video_url)
        record.transcript = result["transcript"]
        record.language = result["language"]

        if not result["transcript"] or len(result["transcript"].strip()) < 10:
            record.status = "COMPLETED"
            record.error_message = "No speech detected in video"
            record.processing_time_seconds = time.time() - start_time
            record.ai_analysis = {"summary": "No speech detected", "suggested_keypoints": []}
            db.commit()
            return _api_response(data=_transcript_to_dict(record))

        # Step 2: Classify
        record.status = "ANALYZING"
        db.commit()

        from app.services.ai_classifier import classify_transcript
        from app.models.account import AdAccount

        branch_name = "Unknown"
        if req.material_id:
            mat = db.query(AdMaterial).filter(AdMaterial.id == req.material_id).first()
            if mat:
                acc = db.query(AdAccount).filter(AdAccount.id == mat.branch_id).first()
                if acc:
                    branch_name = acc.account_name

        analysis = classify_transcript(
            transcript=result["transcript"],
            branch_name=branch_name,
            language=result["language"],
        )

        record.ai_analysis = analysis
        record.status = "COMPLETED"
        record.processing_time_seconds = time.time() - start_time
        db.commit()

        return _api_response(data=_transcript_to_dict(record))

    except Exception as e:
        # Save error state
        try:
            if record:
                record.status = "FAILED"
                record.error_message = str(e)
                db.commit()
        except Exception:
            pass
        return _api_response(error=str(e))


# ──────────────────────────────────────────────
# GET /api/transcripts/{id} — Get transcript status/result
# ──────────────────────────────────────────────
@router.get("/transcripts/{transcript_id}")
def get_transcript(transcript_id: str, db: Session = Depends(get_db)):
    """Get transcription status and result."""
    try:
        record = db.query(VideoTranscript).filter(VideoTranscript.id == transcript_id).first()
        if not record:
            return _api_response(error="Transcript not found")
        return _api_response(data=_transcript_to_dict(record))
    except Exception as e:
        return _api_response(error=str(e))


# ──────────────────────────────────────────────
# GET /api/transcripts — List all transcripts
# ──────────────────────────────────────────────
@router.get("/transcripts")
def list_transcripts(
    material_id: str | None = None,
    combo_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List transcription records with optional filters."""
    try:
        q = db.query(VideoTranscript)
        if material_id:
            q = q.filter(VideoTranscript.material_id == material_id)
        if combo_id:
            q = q.filter(VideoTranscript.combo_id == combo_id)
        if status:
            q = q.filter(VideoTranscript.status == status)

        total = q.count()
        records = q.order_by(VideoTranscript.created_at.desc()).offset(offset).limit(limit).all()

        return _api_response(data={
            "items": [_transcript_to_dict(r) for r in records],
            "total": total,
        })
    except Exception as e:
        return _api_response(error=str(e))


# ──────────────────────────────────────────────
# POST /api/transcribe/batch — Batch transcribe
# ──────────────────────────────────────────────
@router.post("/transcribe/batch")
def batch_transcription(
    req: TranscribeBatchRequest,
    db: Session = Depends(get_db),
):
    """Queue batch transcription for multiple videos."""
    try:
        results = []
        from app.tasks.transcription_tasks import transcribe_and_classify_task

        for item in req.items:
            record = VideoTranscript(
                id=str(uuid.uuid4()),
                video_url=item.video_url,
                material_id=item.material_id,
                combo_id=item.combo_id,
                status="PENDING",
            )
            db.add(record)
            db.flush()

            transcribe_and_classify_task.delay(record.id)
            results.append({
                "transcript_id": record.id,
                "video_url": item.video_url,
                "status": "PENDING",
            })

        db.commit()
        return _api_response(data={
            "queued": len(results),
            "items": results,
        })
    except Exception as e:
        return _api_response(error=str(e))


# ──────────────────────────────────────────────
# POST /api/transcripts/{id}/apply — Apply AI suggestions to combo/angle/keypoints
# ──────────────────────────────────────────────
@router.post("/transcripts/{transcript_id}/apply")
def apply_suggestions(transcript_id: str, db: Session = Depends(get_db)):
    """Apply AI-suggested angle and keypoints to the linked combo.

    Creates/finds matching angle and keypoints, then updates the combo.
    """
    try:
        record = db.query(VideoTranscript).filter(VideoTranscript.id == transcript_id).first()
        if not record:
            return _api_response(error="Transcript not found")
        if record.status != "COMPLETED" or not record.ai_analysis:
            return _api_response(error="Transcription not complete or no AI analysis")
        if not record.combo_id:
            return _api_response(error="No combo linked to this transcript")

        from app.models.ad_angle import AdAngle
        from app.models.keypoint import BranchKeypoint
        from app.services.creative_service import next_angle_id

        combo = db.query(AdCombo).filter(AdCombo.id == record.combo_id).first()
        if not combo:
            return _api_response(error="Linked combo not found")

        analysis = record.ai_analysis
        applied = {"angle": None, "keypoints_added": 0}

        # --- Apply Angle ---
        suggested_type = analysis.get("suggested_angle_type")
        if suggested_type:
            # Check if angle with this type exists for the branch
            existing_angle = (
                db.query(AdAngle)
                .filter(AdAngle.branch_id == combo.branch_id, AdAngle.angle_type == suggested_type)
                .first()
            )
            if existing_angle:
                combo.angle_id = existing_angle.id
                applied["angle"] = existing_angle.angle_id
            else:
                # Create new angle
                new_angle = AdAngle(
                    branch_id=combo.branch_id,
                    angle_id=next_angle_id(db),
                    angle_type=suggested_type,
                    angle_explain=analysis.get("suggested_angle_explain", ""),
                    hook_examples=analysis.get("suggested_hook_examples", []),
                    angle_text=suggested_type,
                    status="TEST",
                    created_by="ai-classifier",
                )
                db.add(new_angle)
                db.flush()
                combo.angle_id = new_angle.id
                applied["angle"] = new_angle.angle_id

        # --- Apply Keypoints ---
        suggested_kps = analysis.get("suggested_keypoints", [])
        kp_ids = list(combo.keypoint_ids or []) if combo.keypoint_ids else []

        for kp_data in suggested_kps:
            category = kp_data.get("category", "experience")
            title = kp_data.get("title", "")
            if not title:
                continue

            # Check if similar keypoint already exists
            existing_kp = (
                db.query(BranchKeypoint)
                .filter(
                    BranchKeypoint.branch_id == combo.branch_id,
                    BranchKeypoint.title == title,
                )
                .first()
            )
            if existing_kp:
                if existing_kp.id not in kp_ids:
                    kp_ids.append(existing_kp.id)
                    applied["keypoints_added"] += 1
            else:
                new_kp = BranchKeypoint(
                    branch_id=combo.branch_id,
                    category=category,
                    title=title,
                    is_active=True,
                )
                db.add(new_kp)
                db.flush()
                kp_ids.append(new_kp.id)
                applied["keypoints_added"] += 1

        combo.keypoint_ids = kp_ids

        # Apply target audience if detected
        if analysis.get("detected_ta") and analysis["detected_ta"] != "null":
            combo.target_audience = analysis["detected_ta"]
            applied["target_audience"] = analysis["detected_ta"]

        db.commit()

        return _api_response(data={
            "applied": applied,
            "combo_id": combo.combo_id,
            "message": "AI suggestions applied to combo",
        })

    except Exception as e:
        return _api_response(error=str(e))


def _transcript_to_dict(record: VideoTranscript) -> dict:
    return {
        "id": record.id,
        "material_id": record.material_id,
        "combo_id": record.combo_id,
        "video_url": record.video_url,
        "language": record.language,
        "transcript": record.transcript,
        "ai_analysis": record.ai_analysis,
        "status": record.status,
        "error_message": record.error_message,
        "processing_time_seconds": record.processing_time_seconds,
        "triggered_by": record.triggered_by,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
