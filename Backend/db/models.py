from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, LargeBinary


class Base(DeclarativeBase):
    pass


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