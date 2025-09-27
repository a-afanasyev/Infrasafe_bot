# User Profile Management API endpoints
# UK Management Bot - User Service

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.user import (
    UserProfileCreate, UserProfileUpdate, UserProfileResponse
)
from services.profile_service import ProfileService

logger = logging.getLogger(__name__)
router = APIRouter()

def get_profile_service(db: AsyncSession = Depends(get_db)) -> ProfileService:
    return ProfileService(db)

@router.get("/{user_id}", response_model=UserProfileResponse)
async def get_user_profile(
    user_id: int,
    profile_service: ProfileService = Depends(get_profile_service)
):
    """
    Get user profile by user ID
    """
    try:
        profile = await profile_service.get_profile(user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        return profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user profile error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{user_id}", response_model=UserProfileResponse)
async def create_user_profile(
    user_id: int,
    profile_data: UserProfileCreate,
    profile_service: ProfileService = Depends(get_profile_service)
):
    """
    Create user profile
    """
    try:
        profile = await profile_service.create_profile(user_id, profile_data)
        return profile
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Create user profile error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put("/{user_id}", response_model=UserProfileResponse)
async def update_user_profile(
    user_id: int,
    profile_update: UserProfileUpdate,
    profile_service: ProfileService = Depends(get_profile_service)
):
    """
    Update user profile
    """
    try:
        profile = await profile_service.update_profile(user_id, profile_update.model_dump(exclude_unset=True))
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        return profile
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update user profile error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{user_id}/addresses")
async def update_user_addresses(
    user_id: int,
    home_address: Optional[str] = None,
    apartment_address: Optional[str] = None,
    yard_address: Optional[str] = None,
    address_type: Optional[str] = None,
    profile_service: ProfileService = Depends(get_profile_service)
):
    """
    Update user addresses
    """
    try:
        if address_type and address_type not in ['home', 'apartment', 'yard']:
            raise HTTPException(status_code=400, detail="Invalid address type")

        address_data = {
            "home_address": home_address,
            "apartment_address": apartment_address,
            "yard_address": yard_address,
            "address_type": address_type
        }

        # Remove None values
        address_data = {k: v for k, v in address_data.items() if v is not None}

        profile = await profile_service.update_addresses(user_id, address_data)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        return {"message": "Addresses updated successfully", "profile": profile}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update user addresses error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{user_id}/specialization")
async def get_user_specialization(
    user_id: int,
    profile_service: ProfileService = Depends(get_profile_service)
):
    """
    Get user specializations (for executors/managers)
    """
    try:
        specialization = await profile_service.get_specialization(user_id)
        return {"user_id": user_id, "specialization": specialization}
    except Exception as e:
        logger.error(f"Get user specialization error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put("/{user_id}/specialization")
async def update_user_specialization(
    user_id: int,
    specialization: List[str],
    profile_service: ProfileService = Depends(get_profile_service)
):
    """
    Update user specializations
    """
    try:
        profile = await profile_service.update_specialization(user_id, specialization)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        return {"message": "Specialization updated successfully", "profile": profile}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update user specialization error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{user_id}/avatar")
async def upload_user_avatar(
    user_id: int,
    file: UploadFile = File(...),
    profile_service: ProfileService = Depends(get_profile_service)
):
    """
    Upload user avatar image
    """
    try:
        # Validate file type
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")

        # Upload to Media Service and update profile
        avatar_url = await profile_service.upload_avatar(user_id, file)

        return {"message": "Avatar uploaded successfully", "avatar_url": avatar_url}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload user avatar error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/{user_id}/avatar")
async def remove_user_avatar(
    user_id: int,
    profile_service: ProfileService = Depends(get_profile_service)
):
    """
    Remove user avatar
    """
    try:
        success = await profile_service.remove_avatar(user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Profile not found")

        return {"message": "Avatar removed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove user avatar error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{user_id}/completeness")
async def get_profile_completeness(
    user_id: int,
    profile_service: ProfileService = Depends(get_profile_service)
):
    """
    Get profile completion percentage
    """
    try:
        completeness = await profile_service.get_profile_completeness(user_id)
        return {
            "user_id": user_id,
            "completeness_percentage": completeness["percentage"],
            "missing_fields": completeness["missing_fields"],
            "total_fields": completeness["total_fields"],
            "completed_fields": completeness["completed_fields"]
        }
    except Exception as e:
        logger.error(f"Get profile completeness error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")