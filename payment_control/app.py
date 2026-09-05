"""Service-to-service payment API. UK authenticates staff; credentials never enter the browser.

One isolated database/service token per UK accounting perimeter. No cross-tenant IDs.
"""
import hashlib
import json
import os
import secrets
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, delete, insert, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from payment_control.imports import MAX_BYTES, account_number, parse_file
from payment_control.database import database_url as configured_database_url
from payment_control.models import AuditEvent, Base, ImportBatch, ImportEntry, PaymentClaim


def create_app(database_url=None, service_token=None, *, initialize=False):
    url = database_url or configured_database_url()
    token = service_token or os.environ.get("PAYMENT_SERVICE_TOKEN", "")
    if len(token) < 32:
        raise RuntimeError("PAYMENT_SERVICE_TOKEN must contain at least 32 characters")
    engine = create_engine(url, pool_pre_ping=True)
    if initialize:  # isolated tests only; deployment uses the migrate command
        Base.metadata.create_all(engine)
    @asynccontextmanager
    async def lifespan(app):
        try:
            if not set(Base.metadata.tables).issubset(inspect(engine).get_table_names()):
                raise RuntimeError("Run payment migrations before starting the service")
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="Payment Control", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    def db_session():
        with Session(engine) as db:
            yield db

    def actor(x_service_token: str = Header(default=""), x_actor_id: str = Header(default="")):
        if not secrets.compare_digest(x_service_token.encode(), token.encode()):
            raise HTTPException(401, "Unauthorized service")
        if not x_actor_id or len(x_actor_id) > 64:
            raise HTTPException(400, "Actor required")
        return x_actor_id

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/health")
    def health():
        if not set(Base.metadata.tables).issubset(inspect(engine).get_table_names()):
            raise HTTPException(503, "Run payment migrations")
        return {"status": "ok"}

    def batch_out(batch):
        return {key: getattr(batch, key) for key in (
            "id", "kind", "source", "filename", "as_of", "status", "created_at", "created_by", "invalid", "row_count"
        )}

    def detail(db, batch, offset=0):
        rows = db.scalars(select(ImportEntry).where(ImportEntry.batch_id == batch.id).order_by(ImportEntry.line).offset(offset).limit(200)).all()
        audit = db.scalars(select(AuditEvent).where(AuditEvent.batch_id == batch.id).order_by(AuditEvent.id)).all()
        return {**batch_out(batch), "rows": [
            {"line": row.line, "account_number": row.account_number, **row.data, "errors": row.errors} for row in rows
        ], "preview_limit": 200, "offset": offset, "audit": [
            {"action": e.action, "actor_id": e.actor_id, "reason": e.reason, "created_at": e.created_at} for e in audit
        ]}

    def get_batch(db, batch_id, lock=False):
        stmt = select(ImportBatch).where(ImportBatch.id == batch_id)
        batch = db.scalar(stmt.with_for_update() if lock else stmt)
        if batch is None:
            raise HTTPException(404, "Import not found")
        return batch

    @app.post("/v1/imports/preview")
    def preview(
        kind: Literal["balances", "payments"] = Form(...),
        as_of: date = Form(...), source: str = Form(..., min_length=1, max_length=100),
        file: UploadFile = File(...), who=Depends(actor), db=Depends(db_session),
    ):
        source = source.strip()
        if not source:
            raise HTTPException(422, "Укажите источник")
        content = file.file.read(MAX_BYTES + 1)
        try:
            rows = parse_file(file.filename or "", content, kind)
        except (ValueError, UnicodeError, OverflowError) as exc:
            raise HTTPException(422, str(exc)) from exc
        fingerprint = hashlib.sha256(json.dumps([kind, source, as_of.isoformat(), rows], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        existing = db.scalar(select(ImportBatch).where(ImportBatch.fingerprint == fingerprint))
        if existing:
            return detail(db, existing)
        batch = ImportBatch(fingerprint=fingerprint, kind=kind, source=source,
                            filename=Path(file.filename or "upload").name[:200], as_of=as_of,
                            created_by=who, invalid=sum(bool(r["errors"]) for r in rows), row_count=len(rows))
        db.add(batch)
        try:
            db.flush()
            for row in rows:
                db.add(ImportEntry(batch_id=batch.id, line=row["line"], account_number=row["account_number"],
                                   paid_at=_paid_at(row["data"]),
                                   data={**row["data"], "raw": row["raw"]}, errors=row["errors"]))
            db.add(AuditEvent(batch_id=batch.id, action="preview", actor_id=who))
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(select(ImportBatch).where(ImportBatch.fingerprint == fingerprint))
            if not existing:
                raise
            return detail(db, existing)
        return detail(db, batch)

    @app.get("/v1/imports")
    def batches(offset: int = Query(0, ge=0), who=Depends(actor), db=Depends(db_session)):
        return [batch_out(b) for b in db.scalars(select(ImportBatch).order_by(ImportBatch.id.desc()).offset(offset).limit(50))]

    @app.get("/v1/imports/{batch_id}")
    def batch_detail(batch_id: int, offset: int = Query(0, ge=0), who=Depends(actor), db=Depends(db_session)):
        return detail(db, get_batch(db, batch_id), offset)

    @app.post("/v1/imports/{batch_id}/activate")
    def activate(batch_id: int, who=Depends(actor), db=Depends(db_session)):
        batch = get_batch(db, batch_id, lock=True)
        if batch.invalid:
            raise HTTPException(422, "Исправьте ошибки в исходном файле и загрузите его заново")
        if batch.status == "active":
            return detail(db, batch)
        batch.status = "active"
        db.add(AuditEvent(batch_id=batch_id, action="activate", actor_id=who))
        try:
            if batch.kind == "payments":
                # Одной вставкой, а не по строке: до 10 000 строк держали бы row-lock
                # батча всё время поочерёдных INSERT'ов. Вставка внутри try —
                # пересечение операций всплывает здесь же, а не только на commit.
                claims = [{"batch_id": batch_id, "source": batch.source, "operation_id": row.data["operation_id"]}
                          for row in db.scalars(select(ImportEntry).where(ImportEntry.batch_id == batch_id))]
                if claims:
                    db.execute(insert(PaymentClaim), claims)
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "Операция этого источника уже есть в активном импорте. Проверьте пересечение выгрузок.") from exc
        return detail(db, batch)

    class Deactivate(BaseModel):
        reason: str = Field(min_length=3, max_length=500)

    @app.post("/v1/imports/{batch_id}/deactivate")
    def deactivate(batch_id: int, body: Deactivate, who=Depends(actor), db=Depends(db_session)):
        if len(body.reason.strip()) < 3:
            raise HTTPException(422, "Укажите причину")
        batch = get_batch(db, batch_id, lock=True)
        if batch.status != "active":
            raise HTTPException(409, "Импорт не активен — деактивировать нечего")
        batch.status = "inactive"
        db.execute(delete(PaymentClaim).where(PaymentClaim.batch_id == batch_id))
        db.add(AuditEvent(batch_id=batch_id, action="deactivate", actor_id=who, reason=body.reason.strip()))
        db.commit()
        return detail(db, batch)

    @app.get("/v1/account")
    def account(account_number: str = Query(..., min_length=1, max_length=64), who=Depends(actor), db=Depends(db_session)):
        try:
            number = normalize_account(account_number)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        stmt = select(ImportEntry, ImportBatch).join(ImportBatch, ImportEntry.batch_id == ImportBatch.id).where(
            ImportEntry.account_number == number, ImportBatch.status == "active")
        snapshots = db.execute(stmt.where(ImportBatch.kind == "balances").order_by(ImportBatch.as_of.desc(), ImportBatch.id.desc()).limit(50)).all()
        payments = db.execute(stmt.where(ImportBatch.kind == "payments").order_by(
            ImportEntry.paid_at.desc().nullslast(), ImportEntry.id.desc()).limit(200)).all()

        def row_out(row, batch):
            return {**{k: v for k, v in row.data.items() if k != "raw"}, "import_id": batch.id,
                    "source": batch.source, "filename": batch.filename, "as_of": batch.as_of,
                    "imported_at": batch.created_at, "line": row.line, "currency": "UZS"}

        current = row_out(*snapshots[0]) if snapshots else None
        return {"account_number": number, "status": "available" if current else "no_data", "current": current,
                "history": [row_out(*r) for r in snapshots], "payments": [row_out(*r) for r in payments],
                "history_limit": 50, "payments_limit": 200}

    return app


def _paid_at(data):
    """Дата платежа отдельной колонкой; у строк с ошибками её нет."""
    try:
        return date.fromisoformat(data["paid_at"])
    except (KeyError, TypeError, ValueError):
        return None


normalize_account = account_number
