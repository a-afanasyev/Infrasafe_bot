from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uk_management_bot.api.dependencies import get_db, get_current_user, _parse_user_roles
from uk_management_bot.database.models.user import User
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_LANGUAGES = {"ru", "uz"}


class ProfileOut(BaseModel):
    id: int
    telegram_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    language: str = "ru"
    status: str = "pending"
    verification_status: str = "pending"
    roles: Optional[list[str]] = None
    active_role: Optional[str] = None
    model_config = {"from_attributes": True}

    @classmethod
    def from_user(cls, user: User) -> "ProfileOut":
        roles_list = _parse_user_roles(user)
        return cls(
            id=user.id,
            telegram_id=user.telegram_id,
            first_name=user.first_name,
            last_name=user.last_name,
            phone=user.phone,
            email=user.email,
            language=user.language,
            status=user.status,
            verification_status=getattr(user, "verification_status", "pending"),
            roles=roles_list,
            active_role=getattr(user, "active_role", None),
        )


class UpdateProfileBody(BaseModel):
    language: Optional[str] = None
    email: Optional[str] = None


@router.get("", response_model=ProfileOut)
async def get_profile(user: User = Depends(get_current_user)):
    return ProfileOut.from_user(user)


@router.patch("")
async def update_profile(
    body: UpdateProfileBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()

    if body.language is not None:
        if body.language not in ALLOWED_LANGUAGES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"language must be one of: {sorted(ALLOWED_LANGUAGES)}",
            )
        db_user.language = body.language

    if body.email is not None:
        if body.email and "@" not in body.email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format")
        db_user.email = body.email

    await db.commit()
    return {"ok": True}


@router.post("/documents")
async def upload_document(
    document_type: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Read in chunks to enforce size limit
    content = bytearray()
    while True:
        chunk = await file.read(8192)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large (max {MAX_UPLOAD_SIZE // 1024 // 1024} MB)",
            )

    # TODO: integrate with MediaServiceClient
    return {"ok": True, "document_type": document_type, "filename": file.filename}
