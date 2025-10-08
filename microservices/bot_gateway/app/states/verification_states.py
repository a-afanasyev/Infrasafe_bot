"""
User Verification FSM States.

Handles identity verification workflow for executors:
1. Document upload (passport, ID card)
2. Selfie with document
3. Additional documents (if required)
4. Admin review and approval

P0 Priority - CRITICAL FOR EXECUTOR ONBOARDING
"""

from aiogram.fsm.state import State, StatesGroup


class UserVerificationStates(StatesGroup):
    """
    FSM states for user identity verification workflow.

    Flow:
    1. waiting_for_document_type → User selects document type (passport/ID/driver license)
    2. waiting_for_document_photo → User uploads document photo
    3. waiting_for_selfie → User uploads selfie with document
    4. waiting_for_additional_docs → User uploads additional documents (optional)
    5. verification_submitted → Documents submitted for review
    6. verification_approved → Admin approved verification
    7. verification_rejected → Admin rejected verification (can retry)

    Example usage:
        @router.message(UserVerificationStates.waiting_for_document_photo)
        async def process_document(message: Message, state: FSMContext):
            if message.photo:
                photo_id = message.photo[-1].file_id
                await state.update_data(document_photo=photo_id)
                await state.set_state(UserVerificationStates.waiting_for_selfie)
    """

    # Document type selection
    waiting_for_document_type = State()

    # Document photo upload
    waiting_for_document_photo = State()

    # Selfie with document upload
    waiting_for_selfie = State()

    # Additional documents upload (optional)
    waiting_for_additional_docs = State()

    # Verification submitted for review
    verification_submitted = State()

    # Admin is reviewing documents
    under_review = State()

    # Verification approved
    verification_approved = State()

    # Verification rejected (can retry)
    verification_rejected = State()

    # Waiting for rejection reason from admin
    waiting_for_rejection_reason = State()
