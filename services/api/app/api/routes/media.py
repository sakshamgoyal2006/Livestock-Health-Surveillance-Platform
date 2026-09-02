from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.api.deps import CurrentUser, SessionDep, require_roles
from app.core.audit import append_audit
from app.domain.models import (
    HealthReport,
    MediaAsset,
    MediaBlob,
    MediaUploadChunk,
    User,
)
from app.triage.pipeline import run_report_triage
from app.triage.vision import ImageRejected
from app.triage.vision import sanitize_image as sanitize_for_analysis

router = APIRouter(prefix="/api/v1", tags=["media"])
Reporter = Annotated[User, Depends(require_roles("FARMER", "FIELD_WORKER"))]
ALLOWED_MIME = {"image/jpeg": "JPEG", "image/png": "PNG"}
MAX_CHUNK_BYTES = 1024 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000


def sanitize_image(content: bytes, mime_type: str) -> bytes:
    try:
        return sanitize_for_analysis(content, mime_type)
    except ImageRejected as exc:
        raise HTTPException(
            status_code=415 if exc.code == "UNSUPPORTED_MEDIA" else 422,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


async def accessible_report(
    session: AsyncSession, report_id: UUID, actor: User, *, write: bool
) -> HealthReport:
    report = await session.get(HealthReport, report_id)
    if report is None:
        raise HTTPException(
            status_code=404, detail={"code": "REPORT_NOT_FOUND", "message": "Report not found"}
        )
    if write and report.reporter_user_id != actor.id:
        raise HTTPException(
            status_code=404, detail={"code": "REPORT_NOT_FOUND", "message": "Report not found"}
        )
    if (
        not write
        and actor.role not in {"VETERINARIAN", "ADMIN"}
        and report.reporter_user_id != actor.id
    ):
        raise HTTPException(
            status_code=404, detail={"code": "REPORT_NOT_FOUND", "message": "Report not found"}
        )
    return report


@router.post("/media/presign-or-upload", response_model=dict[str, object])
async def upload_media_chunk(
    session: SessionDep,
    actor: Reporter,
    request: Request,
    asset_id: Annotated[UUID, Form()],
    report_id: Annotated[UUID, Form()],
    chunk_index: Annotated[int, Form(ge=0, le=49)],
    total_chunks: Annotated[int, Form(ge=1, le=50)],
    checksum_sha256: Annotated[str, Form(pattern=r"^[a-f0-9]{64}$")],
    file: Annotated[UploadFile, File()],
) -> dict[str, object]:
    report = await accessible_report(session, report_id, actor, write=True)
    if chunk_index >= total_chunks:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_CHUNK_INDEX", "message": "Chunk index exceeds total chunks"},
        )
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail={"code": "UNSUPPORTED_MEDIA", "message": "Only JPEG and PNG are supported"},
        )
    content = await file.read(MAX_CHUNK_BYTES + 1)
    if not content or len(content) > MAX_CHUNK_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"code": "CHUNK_TOO_LARGE", "message": "Chunk must be 1 MiB or smaller"},
        )

    asset = await session.get(MediaAsset, asset_id)
    if asset is None:
        asset = MediaAsset(
            id=asset_id,
            health_report_id=report.id,
            owner_user_id=actor.id,
            media_type="IMAGE",
            storage_key=f"database-dev/{asset_id}",
            mime_type=file.content_type,
            byte_size=0,
            checksum_sha256=checksum_sha256,
            exif_removed=False,
            upload_status="UPLOADING",
            total_chunks=total_chunks,
            uploaded_chunks=0,
        )
        session.add(asset)
        await session.flush()
    elif (
        asset.owner_user_id != actor.id
        or asset.health_report_id != report.id
        or asset.checksum_sha256 != checksum_sha256
        or asset.total_chunks != total_chunks
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "MEDIA_CONFLICT", "message": "Media upload identity was reused"},
        )
    elif asset.upload_status == "COMPLETE":
        return {
            "asset_id": str(asset.id),
            "status": asset.upload_status,
            "uploaded_chunks": asset.uploaded_chunks,
            "total_chunks": asset.total_chunks,
            "complete": True,
        }
    existing = await session.scalar(
        select(MediaUploadChunk).where(
            MediaUploadChunk.media_asset_id == asset.id,
            MediaUploadChunk.chunk_index == chunk_index,
        )
    )
    if existing is not None and existing.content != content:
        raise HTTPException(
            status_code=409,
            detail={"code": "CHUNK_CONFLICT", "message": "Chunk content changed during retry"},
        )
    if existing is None:
        session.add(
            MediaUploadChunk(media_asset_id=asset.id, chunk_index=chunk_index, content=content)
        )
        await session.flush()
    chunks = (
        await session.scalars(
            select(MediaUploadChunk)
            .where(MediaUploadChunk.media_asset_id == asset.id)
            .order_by(MediaUploadChunk.chunk_index)
        )
    ).all()
    asset.uploaded_chunks = len(chunks)
    completed = len(chunks) == total_chunks
    if completed:
        combined = b"".join(chunk.content for chunk in chunks)
        if (
            len(combined) > MAX_IMAGE_BYTES
            or hashlib.sha256(combined).hexdigest() != checksum_sha256
        ):
            asset.upload_status = "FAILED"
            await session.commit()
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "MEDIA_CHECKSUM_FAILED",
                    "message": "Media checksum or total size is invalid",
                },
            )
        clean = sanitize_image(combined, file.content_type)
        session.add(MediaBlob(media_asset_id=asset.id, content=clean))
        asset.byte_size = len(clean)
        asset.exif_removed = True
        asset.upload_status = "COMPLETE"
        await append_audit(
            session,
            actor_user_id=actor.id,
            action="MEDIA_UPLOAD_COMPLETED",
            resource_type="media_asset",
            resource_id=asset.id,
            request_id=request.state.request_id,
            details={"mime_type": file.content_type, "exif_removed": True},
        )
    await session.commit()
    if completed:
        await run_report_triage(
            session,
            report.id,
            request_id=request.state.request_id,
            actor_user_id=actor.id,
        )
    return {
        "asset_id": str(asset.id),
        "status": asset.upload_status,
        "uploaded_chunks": asset.uploaded_chunks,
        "total_chunks": asset.total_chunks,
        "complete": completed,
    }


@router.get("/media/{asset_id}")
async def download_media(
    asset_id: UUID, session: SessionDep, actor: CurrentUser
) -> StreamingResponse:
    asset = await session.get(MediaAsset, asset_id)
    if asset is None or asset.upload_status != "COMPLETE":
        raise HTTPException(
            status_code=404, detail={"code": "MEDIA_NOT_FOUND", "message": "Media not found"}
        )
    await accessible_report(session, asset.health_report_id, actor, write=False)
    blob = await session.scalar(select(MediaBlob).where(MediaBlob.media_asset_id == asset.id))
    if blob is None:
        raise HTTPException(
            status_code=404, detail={"code": "MEDIA_NOT_FOUND", "message": "Media not found"}
        )
    return StreamingResponse(BytesIO(blob.content), media_type=asset.mime_type)
