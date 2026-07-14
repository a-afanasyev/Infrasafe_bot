"""Import endpoints: preview (upload) and commit (ТЗ §5.5)."""

import base64
import binascii
import hashlib
import json
from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.periods import get_period_or_404
from app.core.audit import write_audit
from app.core.deps import OPERATOR_ROLES, require_roles
from app.core.deps import correlation_id as _cid
from app.core.errors import bad_request
from app.core.ratelimit import HEAVY_LIMIT, limiter
from app.db import get_db
from app.models import User
from app.services.imports import build_preview, commit_rows, parse_file
from app.services.readings import EDITABLE_PERIOD_STATUSES

router = APIRouter(prefix="/imports/readings", tags=["imports"])


@router.post("/preview", response_model=dict)
@limiter.limit(HEAVY_LIMIT)
async def preview_import(
    request: Request,
    month: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*OPERATOR_ROLES)),
):
    period = get_period_or_404(db, user, month)
    if period.status not in EDITABLE_PERIOD_STATUSES:
        raise bad_request(f"Период {month} в статусе {period.status}: импорт невозможен")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise bad_request("Файл больше 5 МБ")
    raw_rows = parse_file(file.filename or "upload.csv", content)
    if not raw_rows:
        raise bad_request("Файл пуст")
    rows = build_preview(db, user.tenant_id, month, raw_rows)
    payload = [asdict(r) for r in rows]
    # Token binds commit to this exact previewed content
    token_source = json.dumps(payload, default=str, sort_keys=True).encode()
    token = base64.b64encode(
        hashlib.sha256(token_source).digest()[:12] + token_source
    ).decode()
    return {
        "data": {
            "month": month,
            "total": len(rows),
            "valid": sum(1 for r in rows if r.ok),
            "invalid": sum(1 for r in rows if not r.ok),
            "rows": json.loads(json.dumps(payload, default=str)),
            "commit_token": token,
        }
    }


class CommitIn(BaseModel):
    month: str
    commit_token: str
    skip_lines: list[int] = []


@router.post("/commit", response_model=dict)
def commit_import(
    payload: CommitIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*OPERATOR_ROLES)),
):
    period = get_period_or_404(db, user, payload.month)
    if period.status not in EDITABLE_PERIOD_STATUSES:
        raise bad_request(f"Период {payload.month} в статусе {period.status}: импорт невозможен")

    try:
        decoded = base64.b64decode(payload.commit_token.encode())
        digest, token_source = decoded[:12], decoded[12:]
        if hashlib.sha256(token_source).digest()[:12] != digest:
            raise ValueError
        previewed = json.loads(token_source)
    except (ValueError, binascii.Error, json.JSONDecodeError):
        raise bad_request("Недействительный commit_token: повторите предпросмотр")

    # SEC-03: re-derive rows server-side from the user-supplied input ONLY; never
    # trust client-provided meter_id/errors/parsed_* from the token. build_preview
    # re-looks up the meter tenant-scoped and re-runs every validation rule.
    raw_rows = [
        {
            "meter_number": item.get("meter_number", ""),
            "period": item.get("period", ""),
            "reading_value": item.get("reading_value", ""),
            "read_at": item.get("read_at", ""),
            "note": item.get("note", ""),
            "missing_reason": item.get("missing_reason", ""),
        }
        for item in previewed
    ]
    rows = build_preview(db, user.tenant_id, payload.month, raw_rows)
    rows = [r for r in rows if r.line not in payload.skip_lines]

    saved = commit_rows(db, user, period, rows)
    write_audit(db, user=user, entity_type="period", entity_id=period.id, action="import_commit",
                after={"month": payload.month, "saved": saved}, correlation_id=_cid(request))
    db.commit()
    return {"data": {"saved": saved, "skipped": len(rows) - saved}}
