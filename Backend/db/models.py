from datetime import datetime

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, LargeBinary, func
from sqlalchemy.types import DateTime


class Base(DeclarativeBase):
    pass


class Job(Base):
    """Durable status record for one pipeline run.

    Keyed by the UUID job_id so each run (and therefore each user) stays
    isolated. Persisted so status survives backend restarts/redeploys and is
    visible regardless of which worker handles the status poll.
    """
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(primary_key=True)            # UUID job_id
    status: Mapped[str] = mapped_column(default="running")        # running | done | error
    message: Mapped[str] = mapped_column(default="")
    progress: Mapped[int] = mapped_column(default=0)
    paper_id: Mapped[int | None]
    error: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Paper(Base):
    __tablename__ = "papers"
    id: Mapped[int] = mapped_column(primary_key=True)
    board: Mapped[str | None]
    level: Mapped[str | None]
    subject: Mapped[str | None]
    year: Mapped[str | None]
    paper_code: Mapped[str | None]
    paper_number: Mapped[int | None]
    tier: Mapped[str | None]

    questions: Mapped[list["Question"]] = relationship(back_populates="paper")


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"))
    question_number: Mapped[str]
    question_text: Mapped[str]
    marks: Mapped[int | None]
    answer: Mapped[str | None]
    mark_breakdown: Mapped[str | None]
    additional_guidance: Mapped[str | None]
    eval_prompt: Mapped[str | None]
    verification_status: Mapped[str | None]

    paper: Mapped["Paper"] = relationship(back_populates="questions")
    answers: Mapped[list["Answer"]] = relationship(back_populates="question")
    images: Mapped[list["Image"]] = relationship(back_populates="question")


class Answer(Base):
    __tablename__ = "answers"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    category: Mapped[str]
    answer_text: Mapped[str]
    awarded_marks: Mapped[int | None]
    verified: Mapped[bool | None]

    question: Mapped["Question"] = relationship(back_populates="answers")


class Image(Base):
    __tablename__ = "images"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    figure_number: Mapped[str | None]
    image_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    mime_type: Mapped[str] = mapped_column(default="image/png")
    question: Mapped["Question"] = relationship(back_populates="images") 