import hashlib
import secrets

from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import get_settings

SESSION_SALT = "resource-session-v1"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt=SESSION_SALT)


def create_session_token(user_id: str) -> str:
    return _serializer().dumps({"uid": user_id})


def read_session_token(token: str) -> str | None:
    try:
        payload = _serializer().loads(token, max_age=get_settings().session_ttl_seconds)
    except BadSignature:
        return None
    return payload.get("uid")


def generate_ticket_token() -> str:
    return secrets.token_urlsafe(48)


def hash_ticket_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
