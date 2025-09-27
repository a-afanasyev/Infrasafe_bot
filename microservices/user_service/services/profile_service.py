# Profile Service - User Profile Management
# UK Management Bot - User Service

import logging
from typing import List, Optional, Dict, Any
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile
import httpx

from models.user import User, UserProfile
from schemas.user import UserProfileCreate, UserProfileResponse

logger = logging.getLogger(__name__)

class ProfileService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_profile(self, user_id: int) -> Optional[UserProfileResponse]:
        """Get user profile"""
        query = select(UserProfile).where(UserProfile.user_id == user_id)
        result = await self.db.execute(query)
        profile = result.scalar_one_or_none()

        if not profile:
            return None

        return UserProfileResponse(
            id=profile.id,
            user_id=profile.user_id,
            birth_date=profile.birth_date,
            passport_series=profile.passport_series,
            passport_number=profile.passport_number,
            home_address=profile.home_address,
            apartment_address=profile.apartment_address,
            yard_address=profile.yard_address,
            address_type=profile.address_type,
            specialization=profile.specialization,
            bio=profile.bio,
            avatar_url=profile.avatar_url,
            created_at=profile.created_at,
            updated_at=profile.updated_at
        )

    async def create_profile(self, user_id: int, profile_data: UserProfileCreate) -> UserProfileResponse:
        """Create user profile"""
        # Check if user exists
        user_query = select(User).where(User.id == user_id)
        user_result = await self.db.execute(user_query)
        user = user_result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User with ID {user_id} not found")

        # Check if profile already exists
        existing_profile = await self.get_profile(user_id)
        if existing_profile:
            raise ValueError(f"Profile for user {user_id} already exists")

        # Create profile
        profile = UserProfile(
            user_id=user_id,
            birth_date=profile_data.birth_date,
            passport_series=profile_data.passport_series,
            passport_number=profile_data.passport_number,
            home_address=profile_data.home_address,
            apartment_address=profile_data.apartment_address,
            yard_address=profile_data.yard_address,
            address_type=profile_data.address_type,
            specialization=profile_data.specialization or [],
            bio=profile_data.bio,
            avatar_url=profile_data.avatar_url
        )

        self.db.add(profile)
        await self.db.commit()
        await self.db.refresh(profile)

        logger.info(f"Created profile for user {user_id}")

        return await self.get_profile(user_id)

    async def update_profile(self, user_id: int, update_data: Dict[str, Any]) -> Optional[UserProfileResponse]:
        """Update user profile"""
        query = update(UserProfile).where(UserProfile.user_id == user_id).values(**update_data)
        result = await self.db.execute(query)

        if result.rowcount == 0:
            return None

        await self.db.commit()

        logger.info(f"Updated profile for user {user_id} with data: {update_data}")

        return await self.get_profile(user_id)

    async def update_addresses(self, user_id: int, address_data: Dict[str, Any]) -> Optional[UserProfileResponse]:
        """Update user addresses"""
        return await self.update_profile(user_id, address_data)

    async def get_specialization(self, user_id: int) -> List[str]:
        """Get user specializations"""
        query = select(UserProfile.specialization).where(UserProfile.user_id == user_id)
        result = await self.db.execute(query)
        specialization = result.scalar_one_or_none()

        return specialization or []

    async def update_specialization(self, user_id: int, specialization: List[str]) -> Optional[UserProfileResponse]:
        """Update user specializations"""
        # Validate specializations
        valid_specializations = [
            "plumbing", "electrical", "cleaning", "gardening", "maintenance",
            "security", "concierge", "repair", "painting", "hvac", "carpentry", "general"
        ]

        for spec in specialization:
            if spec not in valid_specializations:
                raise ValueError(f"Invalid specialization: {spec}. Must be one of: {valid_specializations}")

        return await self.update_profile(user_id, {"specialization": specialization})

    async def upload_avatar(self, user_id: int, file: UploadFile) -> str:
        """Upload user avatar to Media Service"""
        try:
            # Read file content
            file_content = await file.read()

            # Prepare upload data
            files = {
                "file": (file.filename, file_content, file.content_type)
            }

            data = {
                "user_id": user_id,
                "file_type": "avatar",
                "category": "user_avatars"
            }

            # Upload to Media Service
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://media-service:8000/api/v1/upload",
                    files=files,
                    data=data,
                    timeout=30.0
                )

                if response.status_code != 200:
                    raise ValueError(f"Failed to upload avatar: {response.text}")

                upload_result = response.json()
                avatar_url = upload_result["file_url"]

            # Update profile with avatar URL
            await self.update_profile(user_id, {"avatar_url": avatar_url})

            logger.info(f"Uploaded avatar for user {user_id}: {avatar_url}")

            return avatar_url

        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Media Service: {e}")
            raise ValueError("Failed to upload avatar - Media Service unavailable")
        except Exception as e:
            logger.error(f"Avatar upload error for user {user_id}: {e}")
            raise ValueError(f"Failed to upload avatar: {str(e)}")

    async def remove_avatar(self, user_id: int) -> bool:
        """Remove user avatar"""
        # Get current avatar URL
        profile = await self.get_profile(user_id)
        if not profile or not profile.avatar_url:
            return False

        try:
            # Delete from Media Service
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"http://media-service:8000/api/v1/files/by-url",
                    params={"file_url": profile.avatar_url},
                    timeout=10.0
                )

                if response.status_code not in [200, 404]:
                    logger.warning(f"Failed to delete avatar from Media Service: {response.text}")

            # Remove from profile
            await self.update_profile(user_id, {"avatar_url": None})

            logger.info(f"Removed avatar for user {user_id}")

            return True

        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Media Service: {e}")
            # Still remove from profile even if Media Service is unavailable
            await self.update_profile(user_id, {"avatar_url": None})
            return True
        except Exception as e:
            logger.error(f"Avatar removal error for user {user_id}: {e}")
            return False

    async def get_profile_completeness(self, user_id: int) -> Dict[str, Any]:
        """Get profile completion percentage"""
        profile = await self.get_profile(user_id)

        if not profile:
            return {
                "percentage": 0,
                "missing_fields": [],
                "total_fields": 0,
                "completed_fields": 0
            }

        # Define required fields for profile completeness
        required_fields = [
            "birth_date", "passport_series", "passport_number",
            "home_address", "specialization", "bio"
        ]

        # Check which fields are completed
        completed_fields = []
        missing_fields = []

        for field in required_fields:
            value = getattr(profile, field, None)
            if value is not None and value != "" and (not isinstance(value, list) or len(value) > 0):
                completed_fields.append(field)
            else:
                missing_fields.append(field)

        # Calculate percentage
        total_fields = len(required_fields)
        completed_count = len(completed_fields)
        percentage = round((completed_count / total_fields) * 100, 1) if total_fields > 0 else 0

        return {
            "percentage": percentage,
            "missing_fields": missing_fields,
            "total_fields": total_fields,
            "completed_fields": completed_count
        }

    async def update_rating(self, user_id: int, new_rating: float) -> Optional[UserProfileResponse]:
        """Update user rating (called by other services)"""
        if new_rating < 0.0 or new_rating > 5.0:
            raise ValueError("Rating must be between 0.0 and 5.0")

        # Rating field doesn't exist in current UserProfile model
        # For now, we'll store it in bio as JSON or skip the update
        logger.warning(f"Rating update requested for user {user_id} but rating field not implemented in model")
        return await self.get_profile(user_id)

    async def get_users_by_specialization(self, specialization: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get users with specific specialization"""
        query = select(UserProfile, User).join(User).where(
            UserProfile.specialization.contains([specialization])
        ).limit(limit)

        result = await self.db.execute(query)
        profiles = result.fetchall()

        users_data = []
        for profile, user in profiles:
            users_data.append({
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "specialization": profile.specialization,
                # rating and experience_years fields don't exist in current model
                "bio": profile.bio,
                "address_type": profile.address_type,
                "status": user.status,
                "is_active": user.is_active
            })

        return users_data

    async def get_profile_statistics(self) -> Dict[str, Any]:
        """Get profile completion statistics"""
        from sqlalchemy import func

        # Total profiles
        total_query = select(func.count(UserProfile.id))
        total_profiles = await self.db.execute(total_query)
        total_profiles = total_profiles.scalar()

        # Profiles with avatar
        avatar_query = select(func.count(UserProfile.id)).where(UserProfile.avatar_url.isnot(None))
        profiles_with_avatar = await self.db.execute(avatar_query)
        profiles_with_avatar = profiles_with_avatar.scalar()

        # Profiles by specialization
        spec_query = select(UserProfile.specialization)
        spec_result = await self.db.execute(spec_query)
        all_specializations = spec_result.scalars().all()

        # Count specializations
        spec_count = {}
        for spec_list in all_specializations:
            if spec_list:
                for spec in spec_list:
                    spec_count[spec] = spec_count.get(spec, 0) + 1

        return {
            "total_profiles": total_profiles,
            "profiles_with_avatar": profiles_with_avatar,
            "avatar_completion_rate": round((profiles_with_avatar / total_profiles) * 100, 1) if total_profiles > 0 else 0,
            "specialization_distribution": spec_count
        }