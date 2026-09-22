"""Import endpoints: preview (upload) and commit (ТЗ §5.5)."""

import json
from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.periods import get_period_or_404
from app.config import get_settings
from app.core.audit import write_audit
from app.core.deps import OPERATOR_ROLES, require_roles
from app.core.deps import correlation_id as _cid
from app.core.errors import bad_request
from app.core.ratelimit import HEAVY_LIMIT, limiter
from app.db import get_db
from app.models import User
from app.services.imports import build_preview, commit_rows, parse_file
from app.services.period_lock import lock_period_with_following
from app.services.readings import EDITABLE_PERIOD_STATUSES

router = APIRouter(prefix="/imports/readings", tags=["imports"])


# A9-P3-3: окно «предпросмотр → применить». Оператор просматривает таблицу
# строк (ошибки, расход) и жмёт «Применить» — это минуты; 30 минут с запасом
# покрывают сверку с бумажным журналом, а после истечения достаточно заново
# загрузить тот же файл. Бессрочный токен позволял применить давно устаревший
# предпросмотр.
COMMIT_TOKEN_MAX_AGE_SECONDS = 30 * 60
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _commit_serializer() -> URLSafeTimedSerializer:
    # AUD6-P2-16(в): раньше токен был base64(sha256(payload)[:12] + payload) —
    # контрольная сумма, которую клиент пересчитывал сам, подменив payload
    # (прав не повышало — валидация серверная, — но давало неограниченный
    # N+1-усилитель). Подпись session_secret'ом закрывает подмену.
    return URLSafeTimedSerializer(get_settings().session_secret, salt="import-commit-token")


def issue_commit_token(user, month: str, rows: list[dict]) -> str:
    """A9-P3-3: токен привязан к {пользователь, тенант, месяц} и несёт метку времени."""
    return _commit_serializer().dumps(
        {"user_id": str(user.id), "tenant_id": str(user.tenant_id), "month": month, "rows": rows}
    )


def read_commit_token(token: str, user, month: str) -> list[dict]:
    """Строки предпросмотра из токена; любой отказ — 400 bad_request (канон сервиса)."""
    try:
        data = _commit_serializer().loads(token, max_age=COMMIT_TOKEN_MAX_AGE_SECONDS)
    except SignatureExpired:
        raise bad_request("Предпросмотр устарел: повторите загрузку файла")
    except BadSignature:
        raise bad_request("Недействительный commit_token: повторите предпросмотр")
    binding = (str(user.id), str(user.tenant_id), month)
    if not isinstance(data, dict) or (data.get("user_id"), data.get("tenant_id"), data.get("month")) != binding:
        raise bad_request("commit_token выдан для другого пользователя или месяца: повторите предпросмотр")
    rows = data.get("rows")
    if not isinstance(rows, list) or not all(isinstance(item, dict) for item in rows):
        raise bad_request("Недействительный commit_token: повторите предпросмотр")
    return rows


@router.post("/preview", response_model=dict)
@limiter.limit(HEAVY_LIMIT)
def preview_import(
    request: Request,
    month: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*OPERATOR_ROLES)),
):
    # A9-P2-13: обычный def — FastAPI выполняет его в threadpool. Раньше async
    # def гонял openpyxl (с проверкой распакованного размера) и SQL
    # build_preview прямо в event loop однопроцессного сервиса.
    period = get_period_or_404(db, user, month)
    if period.status not in EDITABLE_PERIOD_STATUSES:
        raise bad_request(f"Период {month} в статусе {period.status}: импорт невозможен")
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise bad_request("Файл больше 5 МБ")
    raw_rows = parse_file(file.filename or "upload.csv", content)
    if not raw_rows:
        raise bad_request("Файл пуст")
    rows = build_preview(db, user.tenant_id, month, raw_rows)
    # Decimal/date нормализуются в строки заранее — и для ответа, и для токена.
    payload = json.loads(json.dumps([asdict(r) for r in rows], default=str))
    return {
        "data": {
            "month": month,
            "total": len(rows),
            "valid": sum(1 for r in rows if r.ok),
            "invalid": sum(1 for r in rows if not r.ok),
            "rows": payload,
            "commit_token": issue_commit_token(user, month, payload),
        }
    }


class CommitIn(BaseModel):
    month: str
    commit_token: str
    skip_lines: list[int] = []


@router.post("/commit", response_model=dict)
@limiter.limit(HEAVY_LIMIT)  # AUD6-P2-16(б): у preview лимит был, у commit — нет
def commit_import(
    payload: CommitIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*OPERATOR_ROLES)),
):
    period = lock_period_with_following(db, user.tenant_id, payload.month)  # AUD7-COR-04: + следующие открытые
    if period.status not in EDITABLE_PERIOD_STATUSES:
        raise bad_request(f"Период {payload.month} в статусе {period.status}: импорт невозможен")

    previewed = read_commit_token(payload.commit_token, user, payload.month)

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
