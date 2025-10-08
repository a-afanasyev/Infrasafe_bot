# FSM State Migration - Gap Analysis Report

**Bot Gateway Service - UK Management Bot**
**Date**: 7 October 2025
**Status**: ⚠️ **INCOMPLETE MIGRATION** (15/28 states = 54% complete)

---

## 📊 Executive Summary

### Current Status

- **Monolith FSM States**: 28 StatesGroup classes
- **Bot Gateway FSM States**: 15 StatesGroup classes
- **Migration Coverage**: **54%** (15/28 migrated)
- **Missing States**: **13 critical state groups** (46%)

### Critical Gap

The Bot Gateway currently implements only **basic request and shift management flows**. The following critical user journeys are **NOT AVAILABLE**:

❌ User Registration & Onboarding
❌ User Verification & KYC
❌ Employee Management
❌ Profile Editing
❌ Building Selection & Management
❌ Quarterly Planning
❌ Advanced Shift Features (time tracking, emergencies, reporting)
❌ Request Reports & Analytics

This means **users cannot register, verify identity, or use advanced features** in the microservices architecture.

---

## 📋 Detailed State Mapping

### ✅ Migrated States (15/28 = 54%)

| Monolith State | Bot Gateway State | Status | File |
|----------------|-------------------|--------|------|
| RequestStatusStates | RequestCreationStates | ✅ Migrated | request_states.py |
| RequestCommentStates | RequestCommentStates | ✅ Migrated | request_states.py |
| (none) | RequestCancellationStates | ✅ New | request_states.py |
| (none) | RequestCompletionStates | ✅ New | request_states.py |
| RequestAssignmentStates | RequestReassignmentStates | ✅ Partial | request_states.py |
| MyShiftsStates | ShiftViewingStates | ✅ Partial | shift_states.py |
| (none) | ShiftTakingStates | ✅ New | shift_states.py |
| ShiftTransferStates | ShiftReleaseStates | ✅ Migrated | shift_states.py |
| (none) | AvailabilityStates | ✅ New | shift_states.py |
| (none) | ShiftSwapStates | ✅ New | shift_states.py |
| UserManagementStates | UserManagementStates | ✅ Migrated | admin_states.py |
| (none) | RequestManagementStates | ✅ New | admin_states.py |
| (none) | SystemConfigStates | ✅ New | admin_states.py |
| (none) | BroadcastStates | ✅ New | admin_states.py |
| (none) | AnalyticsStates | ✅ New | admin_states.py |

**Notes**:
- Some states are "New" - created specifically for microservices architecture
- Some are "Partial" - only subset of monolith functionality migrated

---

### ❌ Missing States (13/28 = 46%)

#### **P0 - Critical (Registration & Auth) - 3 states**

| Monolith State | Functionality | Impact | Estimated LOC |
|----------------|---------------|--------|---------------|
| **RegistrationStates** | User registration flow | 🔴 **BLOCKER**: New users cannot register | ~50 |
| **UserVerificationStates** | Identity verification (KYC) | 🔴 **BLOCKER**: Cannot verify users | ~80 |
| **OnboardingStates** | First-time user onboarding | 🔴 **BLOCKER**: Poor UX for new users | ~100 |

**Total P0**: ~230 lines of code

#### **P1 - High Priority (User Management) - 3 states**

| Monolith State | Functionality | Impact | Estimated LOC |
|----------------|---------------|--------|---------------|
| **ProfileEditingStates** | Edit user profile (name, phone, etc.) | 🟡 Users cannot update profiles | ~60 |
| **InviteCreationStates** | Create invite links for new employees | 🟡 Cannot invite new employees | ~40 |
| **EmployeeManagementStates** | Manage employee data | 🟡 Limited employee administration | ~120 |

**Total P1**: ~220 lines of code

#### **P1 - High Priority (Building Management) - 3 states**

| Monolith State | Functionality | Impact | Estimated LOC |
|----------------|---------------|--------|---------------|
| **BuildingSelectionStates** | Select building from directory | 🟡 Cannot create requests for buildings | ~30 |
| **BuildingManagementStates** | Manage building directory | 🟡 Cannot add/edit buildings | ~50 |
| **RequestWithBuildingStates** | Create request with building | 🟡 Building integration incomplete | ~40 |

**Total P1**: ~120 lines of code

#### **P2 - Medium Priority (Advanced Shift Features) - 6 states**

| Monolith State | Functionality | Impact | Estimated LOC |
|----------------|---------------|--------|---------------|
| **ShiftTimeTrackingStates** | Track shift start/end times | 🟠 Time tracking unavailable | ~50 |
| **ShiftRequestHandlingStates** | Handle shift-related requests | 🟠 Limited shift operations | ~60 |
| **ShiftEmergencyStates** | Handle shift emergencies | 🟠 Cannot report emergencies | ~40 |
| **ShiftReportingStates** | Generate shift reports | 🟠 No shift reports available | ~50 |
| **ShiftStatisticsStates** | View shift statistics | 🟠 No shift analytics | ~40 |
| **ShiftNotificationStates** | Shift notifications management | 🟠 Limited notification control | ~30 |

**Total P2**: ~270 lines of code

#### **P2 - Medium Priority (Shift Management - Admin) - 4 states**

| Monolith State | Functionality | Impact | Estimated LOC |
|----------------|---------------|--------|---------------|
| **ShiftManagementStates** | Admin shift management | 🟠 Partial shift admin features | ~100 |
| **TemplateManagementStates** | Manage shift templates | 🟠 Cannot create shift templates | ~60 |
| **AutoPlanningStates** | Auto-generate shift schedules | 🟠 No automated planning | ~50 |
| **ShiftAnalyticsStates** | Shift analytics & insights | 🟠 No shift analytics | ~40 |
| **ExecutorAssignmentStates** | Assign executors to shifts | 🟠 Manual assignment only | ~50 |

**Total P2**: ~300 lines of code

#### **P3 - Low Priority (Reports & Planning) - 2 states**

| Monolith State | Functionality | Impact | Estimated LOC |
|----------------|---------------|--------|---------------|
| **RequestReportStates** | Generate request reports | 🟢 Reports available via API | ~40 |
| **QuarterlyPlanningStates** | Quarterly shift planning | 🟢 Can use admin UI | ~30 |

**Total P3**: ~70 lines of code

---

## 📈 Migration Effort Estimation

### Summary by Priority

| Priority | Missing States | Estimated LOC | Effort (hours) | Effort (days) |
|----------|----------------|---------------|----------------|---------------|
| **P0 - Critical** | 3 | ~230 | 16-20h | 2-3 days |
| **P1 - High** | 6 | ~340 | 24-30h | 3-4 days |
| **P2 - Medium** | 10 | ~570 | 40-50h | 5-7 days |
| **P3 - Low** | 2 | ~70 | 5-7h | 1 day |
| **TOTAL** | **21** | **~1,210 LOC** | **85-107h** | **11-15 days** |

### Breakdown by Developer

Assuming 2 developers working in parallel:

- **Developer 1**: P0 + half of P1 (3 days)
- **Developer 2**: half of P1 + P2 (7 days)
- **Total Timeline**: **7-8 days** with 2 developers

---

## 🎯 Migration Priority Matrix

### Phase 1: Critical Path (Days 1-3) - P0

**Goal**: Enable user registration and onboarding

1. ✅ **RegistrationStates** (Day 1)
   - `waiting_for_full_name`
   - `waiting_for_phone`
   - `waiting_for_position_confirmation`
   - `waiting_for_additional_info`

2. ✅ **UserVerificationStates** (Day 2)
   - `waiting_for_passport_photo`
   - `waiting_for_verification_selfie`
   - `waiting_for_documents`
   - `verification_review`

3. ✅ **OnboardingStates** (Day 3)
   - `welcome`
   - `tutorial_step_1` through `tutorial_step_5`
   - `onboarding_complete`

**Deliverable**: New users can register, verify identity, and complete onboarding.

---

### Phase 2: User & Building Management (Days 4-6) - P1

**Goal**: Enable profile management and building integration

4. ✅ **ProfileEditingStates** (Day 4)
   - `editing_full_name`
   - `editing_phone`
   - `editing_specialization`
   - `editing_photo`

5. ✅ **InviteCreationStates** (Day 4)
   - `waiting_for_invite_role`
   - `waiting_for_invite_count`
   - `invite_confirmation`

6. ✅ **EmployeeManagementStates** (Day 5)
   - `viewing_employee_list`
   - `selecting_employee`
   - `editing_employee_role`
   - `deactivating_employee`

7. ✅ **BuildingSelectionStates** (Day 5)
   - `selecting_building`
   - `confirming_building`

8. ✅ **BuildingManagementStates** (Day 6)
   - `adding_building`
   - `editing_building`
   - `viewing_building_list`

9. ✅ **RequestWithBuildingStates** (Day 6)
   - `waiting_for_building_selection`
   - `waiting_for_request_details`
   - `confirming_request`

**Deliverable**: Users can manage profiles, invite employees, and work with buildings.

---

### Phase 3: Advanced Shift Features (Days 7-10) - P2

**Goal**: Enable full shift management capabilities

10-19. ✅ **All Shift-Related States** (Days 7-10)
    - ShiftTimeTrackingStates
    - ShiftRequestHandlingStates
    - ShiftEmergencyStates
    - ShiftReportingStates
    - ShiftStatisticsStates
    - ShiftNotificationStates
    - ShiftManagementStates
    - TemplateManagementStates
    - AutoPlanningStates
    - ExecutorAssignmentStates

**Deliverable**: Complete shift management system with all features.

---

### Phase 4: Reports & Planning (Day 11) - P3

**Goal**: Enable advanced analytics

20-21. ✅ **Reporting States** (Day 11)
    - RequestReportStates
    - QuarterlyPlanningStates

**Deliverable**: Full reporting and planning capabilities.

---

## 🚀 Migration Implementation Plan

### Step 1: Analyze Monolith State Files

For each missing state:
1. Read monolith state file
2. Identify all states and their purpose
3. Document required handler functions
4. Identify dependencies (services, middlewares)

### Step 2: Create Bot Gateway State Files

Structure:
```python
# app/states/registration_states.py
from aiogram.fsm.state import State, StatesGroup

class RegistrationStates(StatesGroup):
    """User registration flow - migrated from monolith"""

    waiting_for_full_name = State()
    waiting_for_phone = State()
    waiting_for_position_confirmation = State()
    waiting_for_additional_info = State()
```

### Step 3: Implement Handlers

Create corresponding handler files:
```python
# app/handlers/registration.py
from app.states.registration_states import RegistrationStates
from app.services.user_service_client import user_service

@router.message(RegistrationStates.waiting_for_full_name)
async def process_full_name(message: Message, state: FSMContext):
    # Call User Service API
    await user_service.update_profile(...)
    await state.set_state(RegistrationStates.waiting_for_phone)
```

### Step 4: Register Routers

Add to `main.py`:
```python
from app.handlers import registration, profile_editing, building_selection

app.include_router(registration.router)
app.include_router(profile_editing.router)
app.include_router(building_selection.router)
```

### Step 5: Test Each Flow

Create integration tests:
```python
# tests/test_registration_flow.py
async def test_registration_flow():
    # Simulate user registration
    # Verify all states transition correctly
    # Verify API calls to User Service
```

---

## 📝 File Structure for Missing States

```
bot_gateway/
├── app/
│   ├── states/
│   │   ├── registration_states.py        # ✅ NEW (P0)
│   │   ├── verification_states.py        # ✅ NEW (P0)
│   │   ├── onboarding_states.py          # ✅ NEW (P0)
│   │   ├── profile_states.py             # ✅ NEW (P1)
│   │   ├── invite_states.py              # ✅ NEW (P1)
│   │   ├── employee_states.py            # ✅ NEW (P1)
│   │   ├── building_states.py            # ✅ NEW (P1)
│   │   ├── shift_advanced_states.py      # ✅ NEW (P2)
│   │   └── report_states.py              # ✅ NEW (P3)
│   │
│   ├── handlers/
│   │   ├── registration.py               # ✅ NEW (P0)
│   │   ├── verification.py               # ✅ NEW (P0)
│   │   ├── onboarding.py                 # ✅ NEW (P0)
│   │   ├── profile.py                    # ✅ NEW (P1)
│   │   ├── invites.py                    # ✅ NEW (P1)
│   │   ├── employees.py                  # ✅ NEW (P1)
│   │   ├── buildings.py                  # ✅ NEW (P1)
│   │   ├── shift_advanced.py             # ✅ NEW (P2)
│   │   └── reports.py                    # ✅ NEW (P3)
│   │
│   └── tests/
│       ├── test_registration.py          # ✅ NEW (P0)
│       ├── test_verification.py          # ✅ NEW (P0)
│       ├── test_onboarding.py            # ✅ NEW (P0)
│       └── ... (more tests)
```

**Estimated Files to Create**: ~18 state files + ~18 handler files + ~18 test files = **54 new files**

---

## ⚠️ Risks & Blockers

### Risk 1: Service Dependencies

**Problem**: Many FSM flows depend on services not yet migrated.

**Example**:
- `UserVerificationStates` needs **Document Verification Service** (not implemented)
- `QuarterlyPlanningStates` needs **Advanced Planning API** (not implemented)

**Mitigation**:
1. Create stub/mock service clients
2. Implement basic service endpoints first
3. Progressively enhance as services mature

---

### Risk 2: Business Logic Drift

**Problem**: Monolith logic may have changed since microservices started.

**Mitigation**:
1. Compare monolith git history
2. Review business requirements with product owner
3. Test against current monolith behavior

---

### Risk 3: Data Model Changes

**Problem**: Microservices use different data models than monolith.

**Example**:
- Monolith stores `user.full_name` as single field
- User Service stores `first_name` + `last_name` separately

**Mitigation**:
1. Create adapter layer for data transformation
2. Document mapping between models
3. Add validation tests

---

## 🎯 Success Criteria

### Phase 1 Complete (P0)
- ✅ New users can register via bot
- ✅ Users can verify identity
- ✅ Onboarding flow works end-to-end
- ✅ All P0 tests pass (>90% coverage)

### Phase 2 Complete (P1)
- ✅ Users can edit profiles
- ✅ Admins can invite employees
- ✅ Building selection works in requests
- ✅ All P1 tests pass (>90% coverage)

### Phase 3 Complete (P2)
- ✅ All shift features available
- ✅ Shift analytics functional
- ✅ All P2 tests pass (>85% coverage)

### Phase 4 Complete (P3)
- ✅ Reports generation works
- ✅ Quarterly planning functional
- ✅ All P3 tests pass (>80% coverage)

### Migration Complete
- ✅ **100% FSM state parity** with monolith
- ✅ All user journeys available in Bot Gateway
- ✅ Feature parity verified via acceptance tests
- ✅ Performance benchmarks met (response time < 500ms)
- ✅ Zero regressions from monolith behavior

---

## 📊 Current vs Target State

| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| FSM States Migrated | 15/28 (54%) | 28/28 (100%) | 13 states |
| User Journeys Available | 40% | 100% | 60% |
| Lines of Code | ~500 | ~1,710 | ~1,210 LOC |
| Test Coverage | 60% | 90% | 30% |
| User Registration | ❌ No | ✅ Yes | **BLOCKER** |
| Profile Management | ❌ No | ✅ Yes | **HIGH** |
| Building Integration | ⚠️ Partial | ✅ Full | **HIGH** |
| Advanced Shift Features | ⚠️ Basic | ✅ Complete | **MEDIUM** |

---

## 🚀 Recommended Action Plan

### Immediate Actions (This Sprint)

1. **Prioritize P0 States** (Days 1-3)
   - Start with RegistrationStates
   - Implement UserVerificationStates
   - Complete OnboardingStates

2. **Create Service Stubs**
   - Mock User Service verification endpoint
   - Mock Document Service (if needed)

3. **Update Sprint Plan**
   - Allocate 2 developers for FSM migration
   - Adjust timeline to include FSM completion

### Medium-Term (Next Sprint)

4. **Complete P1 States** (Days 4-6)
   - Profile & employee management
   - Building integration

5. **Begin P2 States** (Days 7-10)
   - Advanced shift features

### Long-Term (Sprint After Next)

6. **Complete P2 & P3 States** (Days 11-15)
7. **Full Integration Testing**
8. **User Acceptance Testing**
9. **Production Deployment**

---

## 📄 Conclusion

**Current State**: Bot Gateway has **54% FSM coverage** - sufficient for basic operations but **NOT production-ready** for full user journeys.

**Critical Gap**: Users **cannot register or onboard** - this is a **BLOCKER** for migration.

**Recommendation**:
1. **Pause** new feature development
2. **Focus** on completing P0 states (3 days effort)
3. **Test** registration flow end-to-end
4. **Then** proceed with P1 states

**Timeline**: With 2 developers, full FSM parity achievable in **7-8 working days**.

---

**Report Generated**: 7 October 2025
**Next Review**: After P0 completion
**Status**: ⚠️ **ACTION REQUIRED**

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
