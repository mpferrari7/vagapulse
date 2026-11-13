from __future__ import annotations

import csv
import io
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Date, DateTime, Enum as SqlEnum, String, create_engine, func, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Stage(StrEnum):
    SAVED = "saved"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"


TRANSITIONS = {
    Stage.SAVED: {Stage.APPLIED, Stage.REJECTED},
    Stage.APPLIED: {Stage.INTERVIEW, Stage.REJECTED},
    Stage.INTERVIEW: {Stage.OFFER, Stage.REJECTED},
    Stage.OFFER: set(),
    Stage.REJECTED: set(),
}


class Base(DeclarativeBase):
    pass


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    company: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(160), nullable=False)
    source: Mapped[str | None] = mapped_column(String(120))
    applied_on: Mapped[date] = mapped_column(Date, nullable=False)
    stage: Mapped[Stage] = mapped_column(
        SqlEnum(Stage, native_enum=False, length=20),
        nullable=False,
        default=Stage.SAVED,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class ApplicationCreate(BaseModel):
    company: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=160)
    source: str | None = Field(default=None, max_length=120)
    applied_on: date = Field(default_factory=date.today)
    stage: Stage = Stage.SAVED

    @field_validator("company", "role", "source")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned and value:
            raise ValueError("O campo nao pode conter apenas espacos.")
        return cleaned or None


class ApplicationStageUpdate(BaseModel):
    stage: Stage


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company: str
    role: str
    source: str | None
    applied_on: date
    stage: Stage
    created_at: datetime


class ApplicationPage(BaseModel):
    items: list[ApplicationRead]
    total: int
    page: int
    page_size: int


class Analytics(BaseModel):
    total: int
    awaiting_response: int
    in_interview: int
    offers: int
    rejected: int
    by_stage: dict[str, int]


def get_session(request: Request):
    with request.app.state.session_factory() as session:
        yield session


SessionDependency = Annotated[Session, Depends(get_session)]


def create_app(database_url: str | None = None) -> FastAPI:
    url = database_url or os.getenv("DATABASE_URL", "sqlite:///./vagapulse.db")
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(
        title="VagaPulse",
        description="API para organizar candidaturas e acompanhar o processo seletivo.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.session_factory = session_factory

    @app.get("/health")
    def health(db: SessionDependency) -> dict[str, str]:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.post(
        "/applications",
        response_model=ApplicationRead,
        status_code=status.HTTP_201_CREATED,
    )
    def create_application(
        data: ApplicationCreate,
        db: SessionDependency,
    ) -> Application:
        application = Application(**data.model_dump())
        db.add(application)
        db.commit()
        db.refresh(application)
        return application

    @app.get("/applications", response_model=ApplicationPage)
    def list_applications(
        db: SessionDependency,
        stage: Stage | None = None,
        q: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> ApplicationPage:
        filters = []
        if stage is not None:
            filters.append(Application.stage == stage)
        if q:
            term = f"%{q.strip()}%"
            filters.append(
                (Application.company.ilike(term)) | (Application.role.ilike(term))
            )
        total = db.scalar(
            select(func.count()).select_from(Application).where(*filters)
        )
        items = db.scalars(
            select(Application)
            .where(*filters)
            .order_by(Application.applied_on.desc(), Application.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return ApplicationPage(
            items=items,
            total=total or 0,
            page=page,
            page_size=page_size,
        )

    @app.get("/applications/export.csv")
    def export_applications(db: SessionDependency) -> Response:
        rows = db.scalars(
            select(Application).order_by(
                Application.applied_on.desc(),
                Application.id.desc(),
            )
        ).all()
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["company", "role", "source", "applied_on", "stage"])
        for item in rows:
            writer.writerow(
                [
                    item.company,
                    item.role,
                    item.source or "",
                    item.applied_on.isoformat(),
                    item.stage.value,
                ]
            )
        return Response(
            content=output.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="vagapulse.csv"'},
        )

    @app.get("/applications/{application_id}", response_model=ApplicationRead)
    def get_application(
        application_id: int,
        db: SessionDependency,
    ) -> Application:
        application = db.get(Application, application_id)
        if application is None:
            raise HTTPException(status_code=404, detail="Candidatura nao encontrada.")
        return application

    @app.patch(
        "/applications/{application_id}/stage",
        response_model=ApplicationRead,
    )
    def update_stage(
        application_id: int,
        data: ApplicationStageUpdate,
        db: SessionDependency,
    ) -> Application:
        application = db.get(Application, application_id)
        if application is None:
            raise HTTPException(status_code=404, detail="Candidatura nao encontrada.")
        if data.stage != application.stage and data.stage not in TRANSITIONS[application.stage]:
            raise HTTPException(
                status_code=409,
                detail=f"Transicao invalida: {application.stage} -> {data.stage}.",
            )
        application.stage = data.stage
        db.commit()
        db.refresh(application)
        return application

    @app.get("/analytics", response_model=Analytics)
    def analytics(db: SessionDependency) -> Analytics:
        grouped = db.execute(
            select(Application.stage, func.count())
            .group_by(Application.stage)
        ).all()
        counts = {stage.value: count for stage, count in grouped}
        by_stage = {stage.value: counts.get(stage.value, 0) for stage in Stage}
        return Analytics(
            total=sum(by_stage.values()),
            awaiting_response=by_stage[Stage.SAVED.value] + by_stage[Stage.APPLIED.value],
            in_interview=by_stage[Stage.INTERVIEW.value],
            offers=by_stage[Stage.OFFER.value],
            rejected=by_stage[Stage.REJECTED.value],
            by_stage=by_stage,
        )

    return app


app = create_app()
