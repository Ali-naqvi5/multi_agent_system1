from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class RunPipelineIn(BaseModel):
    qp_url: str
    qp_metadata_raw: str
    ms_url: str
    ms_metadata_raw: str


class JobStatus(BaseModel):
    job_id: str
    status: str                    # "running" | "done" | "error"
    paper_id: Optional[int] = None
    error: Optional[str] = None
    message: str = ""              # human-readable progress line
    progress: int = 0              # 0–100


class PaperOut(BaseModel):
    id: int
    board: Optional[str] = None
    level: Optional[str] = None
    subject: Optional[str] = None
    year: Optional[str] = None
    paper_code: Optional[str] = None
    tier: Optional[str] = None
    question_count: int = 0

    model_config = {"from_attributes": True}


class AnswerOut(BaseModel):
    id: int
    category: str
    answer_text: str
    awarded_marks: Optional[int] = None
    verified: Optional[bool] = None

    model_config = {"from_attributes": True}


class QuestionOut(BaseModel):
    id: int
    question_number: str
    question_text: str
    marks: Optional[int] = None
    answer: Optional[str] = None
    mark_breakdown: Optional[str] = None
    additional_guidance: Optional[str] = None
    verification_status: Optional[str] = None
    has_image: bool = False
    answers: list[AnswerOut] = []

    model_config = {"from_attributes": True}


class PaperDetailOut(BaseModel):
    id: int
    board: Optional[str] = None
    level: Optional[str] = None
    subject: Optional[str] = None
    year: Optional[str] = None
    paper_code: Optional[str] = None
    tier: Optional[str] = None
    questions: list[QuestionOut] = []

    model_config = {"from_attributes": True}
