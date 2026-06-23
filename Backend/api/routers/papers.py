from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.deps import get_db
from api.schemas import AnswerOut, PaperDetailOut, PaperOut, QuestionOut
from db.models import Image, Paper, Question

router = APIRouter(prefix="/papers", tags=["papers"])


@router.get("", response_model=list[PaperOut])
async def list_papers(db: AsyncSession = Depends(get_db)) -> list[PaperOut]:
    result = await db.execute(select(Paper).order_by(Paper.id.desc()))
    papers = result.scalars().all()

    out = []
    for p in papers:
        count_result = await db.execute(
            select(func.count()).select_from(Question).where(Question.paper_id == p.id)
        )
        po = PaperOut(
            id=p.id,
            board=p.board,
            level=p.level,
            subject=p.subject,
            year=p.year,
            paper_code=p.paper_code,
            tier=p.tier,
            question_count=count_result.scalar() or 0,
        )
        out.append(po)
    return out


@router.get("/{paper_id}", response_model=PaperDetailOut)
async def get_paper(paper_id: int, db: AsyncSession = Depends(get_db)) -> PaperDetailOut:
    result = await db.execute(
        select(Paper)
        .options(
            selectinload(Paper.questions).selectinload(Question.answers),
            selectinload(Paper.questions).selectinload(Question.images),
        )
        .where(Paper.id == paper_id)
    )
    paper = result.scalar_one_or_none()
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")

    questions_out: list[QuestionOut] = []
    for q in sorted(paper.questions, key=lambda x: x.question_number):
        questions_out.append(
            QuestionOut(
                id=q.id,
                question_number=q.question_number,
                question_text=q.question_text,
                marks=q.marks,
                answer=q.answer,
                mark_breakdown=q.mark_breakdown,
                additional_guidance=q.additional_guidance,
                verification_status=q.verification_status,
                has_image=len(q.images) > 0,
                answers=[AnswerOut.model_validate(a) for a in q.answers],
            )
        )

    return PaperDetailOut(
        id=paper.id,
        board=paper.board,
        level=paper.level,
        subject=paper.subject,
        year=paper.year,
        paper_code=paper.paper_code,
        tier=paper.tier,
        questions=questions_out,
    )
