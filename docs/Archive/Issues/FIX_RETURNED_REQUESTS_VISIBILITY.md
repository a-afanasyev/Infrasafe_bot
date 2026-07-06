# Fix: Returned Requests Not Visible to Manager

> _Последнее редактирование: 2025-10-29_

**Date**: 16 October 2025
**Issue**: Returned requests not appearing in manager's "🔄 Возвращённые" section
**Status**: ✅ RESOLVED

## Problem Description

When an applicant returns a request for revision, it wasn't appearing in the manager's "🔄 Возвращённые" (Returned) section. The manager could not see requests that needed to be reviewed after being returned.

**User Report**:
> "сделал возврат заявки но заявка не появилась у менеджера в возвращенных"

## Root Cause

The issue was a **status mismatch** between the return operation and the filter query:

1. **Return Operation** ([request_acceptance.py:481](uk_management_bot/handlers/request_acceptance.py#L481)):
   - When a request is returned, the status is explicitly set to `"Исполнено"`
   - Comment: "Возвращаем в статус 'Исполнено' для повторной проверки менеджером"

2. **Filter Query** ([admin.py:1112](uk_management_bot/handlers/admin.py#L1112)):
   - The returned requests filter was looking for `status == "Выполнена"`
   - This mismatch meant returned requests were never found

### Database State Example

Request 251016-001 after return:
```sql
request_number: 251016-001
status: Исполнено          ← Actual status after return
is_returned: true          ✅ Correctly set
manager_confirmed: false   ✅ Correctly set
returned_at: 2025-10-16 08:00:35.740664+00
```

Filter was searching for:
```sql
status == "Выполнена"      ← Wrong status!
```

## Request Status Workflow

Understanding the complete status workflow:

1. **"Новая"** - New request created by applicant
2. **"В работе"** - Accepted by manager, assigned to executor
3. **"Выполнена"** - Completed by executor (waiting for manager confirmation)
4. **"Исполнено"** - Confirmed by manager OR returned by applicant (waiting for manager review)
5. **"Принято"** - Accepted by applicant (final status)
6. **"Отменена"** - Cancelled
7. **"Закуп"** - Purchasing
8. **"Уточнение"** - Clarification needed

**Key Point**: Status "Исполнено" is used for requests that need manager review, whether they are:
- Newly completed by executor and confirmed by manager
- Returned by applicant for revision

## Solution

### 1. Fixed Returned Requests Filter

**File**: [admin.py:1108-1121](uk_management_bot/handlers/admin.py#L1108-L1121)

**Before**:
```python
# Только возвращённые заявки
q = (
    db.query(Request)
    .filter(
        Request.status == "Выполнена",  # ← Wrong status
        Request.is_returned == True
    )
    .order_by(
        Request.returned_at.desc().nullslast(),
        Request.updated_at.desc().nullslast(),
        Request.created_at.desc()
    )
)
```

**After**:
```python
# Только возвращённые заявки
# Статус "Исполнено" - когда заявка возвращена заявителем на доработку
q = (
    db.query(Request)
    .filter(
        Request.status == "Исполнено",  # ✅ Correct status
        Request.is_returned == True
    )
    .order_by(
        Request.returned_at.desc().nullslast(),
        Request.updated_at.desc().nullslast(),
        Request.created_at.desc()
    )
)
```

### 2. Fixed Statistics Count

**File**: [admin.py:1022-1028](uk_management_bot/handlers/admin.py#L1022-L1028)

**Before**:
```python
# Возвращённые = те, что были отправлены обратно исполнителю
returned_count = db.query(Request).filter(
    Request.status == "Выполнена",  # ← Wrong status
    Request.is_returned == True,
    Request.manager_confirmed == False
).count()
```

**After**:
```python
# Возвращённые = те, что были отправлены обратно исполнителю
# Статус "Исполнено" - когда заявка возвращена заявителем на доработку
returned_count = db.query(Request).filter(
    Request.status == "Исполнено",  # ✅ Correct status
    Request.is_returned == True,
    Request.manager_confirmed == False
).count()
```

## Files Modified

1. **uk_management_bot/handlers/admin.py**:
   - Line 1113: Updated returned requests filter status
   - Line 1025: Updated statistics count status
   - Added clarifying comments

## Testing

### Test Scenario 1: Return Request
1. Applicant returns request 251016-001
2. Request status changes to "Исполнено"
3. `is_returned` flag set to `true`
4. Manager opens "🔄 Возвращённые" section
5. ✅ Request now appears in the list

### Test Scenario 2: Statistics Count
1. Manager opens "✅ Исполненные заявки" menu
2. Statistics show "🔄 Возвращённых: X"
3. ✅ Count includes all returned requests with status "Исполнено"

### Verification Query
```sql
SELECT
    request_number,
    status,
    is_returned,
    manager_confirmed,
    returned_at
FROM requests
WHERE is_returned = true
AND status = 'Исполнено'
ORDER BY returned_at DESC;
```

## Related Code Locations

### Return Operation
**File**: [request_acceptance.py:474-481](uk_management_bot/handlers/request_acceptance.py#L474-L481)
```python
# Устанавливаем флаг возврата
old_status = request.status
request.is_returned = True
request.return_reason = return_reason
request.return_media = return_media
request.returned_by = user.id
request.returned_at = datetime.now()
request.status = "Исполнено"  # Возвращаем в статус "Исполнено" для повторной проверки менеджером
```

### All Status Changes in System
```python
# Locations where request.status is set:
# unaccepted_requests.py:202 → "Принято"
# requests.py:2738 → "Закуп"
# requests.py:2917 → "Выполнена"
# requests.py:2976 → "В работе"
# request_acceptance.py:481 → "Исполнено"
# admin.py:485 → "Выполнена"
# admin.py:555 → "Выполнена"
# admin.py:623 → "В работе"
# admin.py:1606 → "В работе"
# admin.py:1838 → "Выполнена"
# admin.py:1947 → "Уточнение"
# admin.py:2035 → "Отменена"
# admin.py:2153 → "В работе"
```

## Impact

✅ **Resolved**: Managers can now see all returned requests that need review
✅ **Statistics Accurate**: Count of returned requests now correct
✅ **Workflow Complete**: Return workflow now fully functional

## Prevention

### Recommendation: Status Constants

To prevent similar status string mismatch issues in the future, consider creating status constants:

```python
# uk_management_bot/constants/request_status.py
class RequestStatus:
    NEW = "Новая"
    IN_PROGRESS = "В работе"
    COMPLETED_BY_EXECUTOR = "Выполнена"
    CONFIRMED_BY_MANAGER = "Исполнено"
    ACCEPTED = "Принято"
    CANCELLED = "Отменена"
    PURCHASING = "Закуп"
    CLARIFICATION = "Уточнение"
```

This would make the code:
```python
Request.status == RequestStatus.CONFIRMED_BY_MANAGER
```

Instead of:
```python
Request.status == "Исполнено"  # Risk of typo
```

## Additional Notes

- This fix aligns with the return operation's intention to set status to "Исполнено"
- The status "Исполнено" represents "work completed and awaiting manager review"
- This applies both to newly completed requests and returned requests
- The `is_returned` flag differentiates between the two cases

## References

- Issue reported: Session continuation from previous context
- Related fixes: FIX_COMPLETED_REQUESTS_FILTERING.md
- Status workflow: See CLAUDE.md project documentation
