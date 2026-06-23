from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from db.models import Image

router = APIRouter(prefix="/questions", tags=["images"])


@router.get("/{question_id}/image")
async def get_question_image(question_id: int, db: AsyncSession = Depends(get_db)) -> Response:
    result = await db.execute(
        select(Image).where(Image.question_id == question_id).limit(1)
    )
    img = result.scalar_one_or_none()
    if img is None:
        raise HTTPException(status_code=404, detail="No image for this question")
    return Response(content=img.image_bytes, media_type=img.mime_type)
