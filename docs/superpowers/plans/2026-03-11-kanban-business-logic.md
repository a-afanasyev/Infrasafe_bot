# Kanban Business Logic Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement full business logic for request lifecycle — status transition modals with mandatory fields, working action buttons in RequestDetailModal, TWA accept/return flow, CallCenter fixes, and employee block/assign.

**Architecture:** Intercept Kanban drag-and-drop events to show contextual modals before API calls; expand RequestDetailModal from read-only to interactive; fix TWA accept/return to send required data; wire up stub buttons on employee cards.

**Tech Stack:** React 18, TypeScript, @tanstack/react-query, @dnd-kit/core, FastAPI (Python), SQLAlchemy async

---

## Chunk 1: Backend API Additions

### Task 1: Extend UpdateRequestBody + add executor_name to RequestCard

**Context:** API schema `UpdateRequestBody` is missing `requested_materials` and `return_reason`. `RequestCard` doesn't expose `executor_name` — frontend references it but always gets `undefined`.

**Files:**
- Modify: `uk_management_bot/api/requests/schemas.py`
- Modify: `uk_management_bot/api/requests/router.py`

- [ ] **Step 1: Add fields to UpdateRequestBody**

In `uk_management_bot/api/requests/schemas.py`, extend `UpdateRequestBody`:

```python
class UpdateRequestBody(BaseModel):
    status: Optional[str] = None
    executor_id: Optional[int] = None
    notes: Optional[str] = None
    completion_report: Optional[str] = None
    manager_confirmed: Optional[bool] = None
    manager_confirmation_notes: Optional[str] = None
    requested_materials: Optional[str] = None   # ← new: "что купить" for Закуп
    return_reason: Optional[str] = None          # ← new: reason when resident returns
```

- [ ] **Step 2: Add executor_name to RequestCard schema**

In `uk_management_bot/api/requests/schemas.py`, add to `RequestCard`:

```python
class RequestCard(BaseModel):
    request_number: str
    status: str
    category: str
    urgency: Optional[str] = None
    source: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    apartment_id: Optional[int] = None
    executor_id: Optional[int] = None
    executor_name: Optional[str] = None          # ← new: resolved from JOIN
    requested_materials: Optional[str] = None    # ← new: expose to frontend
    completion_report: Optional[str] = None      # ← new: expose to frontend
    return_reason: Optional[str] = None          # ← new: expose to frontend
    notes: Optional[str] = None                  # ← new: expose clarification question
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    manager_confirmed: bool = False

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: Populate executor_name in kanban endpoint with JOIN**

In `uk_management_bot/api/requests/router.py`, modify `get_kanban` to join User:

```python
from sqlalchemy.orm import aliased

@router.get("/kanban", response_model=KanbanResponse)
async def get_kanban(
    executor_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ExecutorUser = aliased(User)
    query = (
        select(Request, ExecutorUser)
        .outerjoin(ExecutorUser, Request.executor_id == ExecutorUser.id)
    )
    if executor_id:
        query = query.filter(Request.executor_id == executor_id)
    if category:
        query = query.filter(Request.category == category)

    result = await db.execute(query.order_by(Request.created_at.desc()).limit(500))
    rows = result.all()

    def _make_card(req: Request, exec_user) -> RequestCard:
        card = RequestCard.model_validate(req)
        if exec_user:
            name = f"{exec_user.first_name or ''} {exec_user.last_name or ''}".strip()
            card.executor_name = name or None
        return card

    columns = []
    for st in KANBAN_STATUSES:
        st_cards = [_make_card(r, eu) for r, eu in rows if r.status == st]
        columns.append(KanbanColumn(status=st, count=len(st_cards), requests=st_cards))
    return KanbanResponse(columns=columns)
```

- [ ] **Step 4: Also populate executor_name in get_request (single card)**

In `router.py`, modify `get_request`:

```python
@router.get("/{request_number}", response_model=RequestCard)
async def get_request(
    request_number: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ExecutorUser = aliased(User)
    result = await db.execute(
        select(Request, ExecutorUser)
        .outerjoin(ExecutorUser, Request.executor_id == ExecutorUser.id)
        .where(Request.request_number == request_number)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    req, exec_user = row
    card = RequestCard.model_validate(req)
    if exec_user:
        name = f"{exec_user.first_name or ''} {exec_user.last_name or ''}".strip()
        card.executor_name = name or None
    return card
```

- [ ] **Step 5: Restart API container and verify**

```bash
docker compose restart api
# Test:
curl -s -H "Authorization: Bearer <token>" http://localhost:8085/api/v2/requests/kanban | python3 -m json.tool | grep executor_name
```

Expected: `executor_name` field present in response (null or string).

- [ ] **Step 6: Commit**

```bash
git add uk_management_bot/api/requests/schemas.py uk_management_bot/api/requests/router.py
git commit -m "feat: extend RequestCard with executor_name, requested_materials, return_reason"
```

---

### Task 2: Add employee block/unblock endpoints

**Context:** `User.status` supports `pending | approved | blocked`. There are `approve` and `reject` endpoints but no `block/unblock`. Frontend "Блок" button needs these.

**Files:**
- Modify: `uk_management_bot/api/shifts/router.py`

- [ ] **Step 1: Add block endpoint after the reject endpoint (~line 190)**

```python
@router.patch("/employees/{user_id}/block", dependencies=[Depends(require_roles("manager"))])
async def block_employee(user_id: int, db: AsyncSession = Depends(get_db)):
    """Block an employee (set status = 'blocked'). Reversible via /unblock."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.status == "blocked":
        raise HTTPException(status_code=409, detail="User is already blocked")
    user.status = "blocked"
    await db.commit()
    return {"message": "blocked"}


@router.patch("/employees/{user_id}/unblock", dependencies=[Depends(require_roles("manager"))])
async def unblock_employee(user_id: int, db: AsyncSession = Depends(get_db)):
    """Unblock an employee (set status back to 'approved')."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.status != "blocked":
        raise HTTPException(status_code=409, detail="User is not blocked")
    user.status = "approved"
    await db.commit()
    return {"message": "unblocked"}
```

- [ ] **Step 2: Restart and verify**

```bash
docker compose restart api
curl -X PATCH -H "Authorization: Bearer <token>" http://localhost:8085/api/v2/shifts/employees/2/block
# Expected: {"message": "blocked"}
curl -X PATCH -H "Authorization: Bearer <token>" http://localhost:8085/api/v2/shifts/employees/2/unblock
# Expected: {"message": "unblocked"}
```

- [ ] **Step 3: Commit**

```bash
git add uk_management_bot/api/shifts/router.py
git commit -m "feat: add employee block/unblock endpoints"
```

---

## Chunk 2: Status Transition Modals

### Task 3: Create TransitionModal component

**Context:** When dragging a card to a new column, `KanbanBoard.tsx` directly calls `PATCH /api/v2/requests/{number}`. We need to intercept and show a modal to collect required data before the API call. The modal varies by target status.

**Files:**
- Create: `frontend/src/components/kanban/TransitionModal.tsx`
- Modify: `frontend/src/components/kanban/KanbanBoard.tsx`

- [ ] **Step 1: Create TransitionModal.tsx**

```typescript
// frontend/src/components/kanban/TransitionModal.tsx
import { useState, useEffect } from 'react'
import { useEmployees } from '../../hooks/useEmployees'

export interface TransitionData {
  status: string
  executor_id?: number
  notes?: string                // clarification question for Уточнение
  requested_materials?: string // what to buy for Закуп
  completion_report?: string   // report text for Выполнена
}

interface Props {
  requestNumber: string
  targetStatus: string
  onConfirm: (data: TransitionData) => void
  onCancel: () => void
}

export default function TransitionModal({ requestNumber, targetStatus, onConfirm, onCancel }: Props) {
  const [executorId, setExecutorId] = useState<number | 'duty' | ''>('')
  const [text, setText] = useState('')
  const { data: employees = [] } = useEmployees({ verification_status: 'verified' })

  // Reset when targetStatus changes
  useEffect(() => {
    setExecutorId('')
    setText('')
  }, [targetStatus])

  const isValid = (): boolean => {
    if (targetStatus === 'В работе') return executorId !== ''
    if (targetStatus === 'Закуп') return text.trim().length > 0
    if (targetStatus === 'Уточнение') return text.trim().length > 0
    if (targetStatus === 'Выполнена') return text.trim().length > 0
    return true
  }

  const handleConfirm = () => {
    const data: TransitionData = { status: targetStatus }
    if (targetStatus === 'В работе') {
      if (executorId === 'duty') {
        // duty = no specific executor_id, just set status
      } else {
        data.executor_id = executorId as number
      }
    }
    if (targetStatus === 'Закуп') data.requested_materials = text.trim()
    if (targetStatus === 'Уточнение') data.notes = text.trim()
    if (targetStatus === 'Выполнена') data.completion_report = text.trim()
    onConfirm(data)
  }

  const TITLES: Record<string, string> = {
    'В работе': 'Назначить исполнителя',
    'Закуп': 'Что необходимо купить?',
    'Уточнение': 'Вопрос к жителю',
    'Выполнена': 'Отчёт о выполнении',
  }

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]"
      onClick={onCancel}
    >
      <div
        className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <h3 className="font-bold text-lg mb-4">
          {TITLES[targetStatus] ?? `Перевод в "${targetStatus}"`}
        </h3>

        {targetStatus === 'В работе' && (
          <div className="space-y-2">
            <p className="text-sm text-gray-600 mb-3">Выберите исполнителя:</p>
            <button
              onClick={() => setExecutorId('duty')}
              className={`w-full text-left border rounded-xl p-3 text-sm transition-colors ${
                executorId === 'duty' ? 'border-blue-500 bg-blue-50 text-blue-700' : 'hover:bg-gray-50'
              }`}
            >
              <span className="font-medium">Дежурный</span>
              <span className="text-gray-400 text-xs ml-2">— назначить дежурному</span>
            </button>
            <div className="text-xs text-gray-400 text-center py-1">или конкретный специалист:</div>
            <div className="max-h-48 overflow-y-auto space-y-1">
              {employees.map(emp => {
                const name = [emp.first_name, emp.last_name].filter(Boolean).join(' ') || `#${emp.id}`
                return (
                  <button
                    key={emp.id}
                    onClick={() => setExecutorId(emp.id)}
                    className={`w-full text-left border rounded-xl p-3 text-sm transition-colors ${
                      executorId === emp.id ? 'border-blue-500 bg-blue-50 text-blue-700' : 'hover:bg-gray-50'
                    }`}
                  >
                    <span className="font-medium">{name}</span>
                    {emp.active_shift_id && (
                      <span className="ml-2 text-xs text-green-600">● На смене</span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {targetStatus === 'Закуп' && (
          <div>
            <p className="text-sm text-gray-600 mb-2">Опишите что нужно купить:</p>
            <textarea
              className="w-full border rounded-xl p-3 text-sm min-h-[100px] focus:outline-none focus:border-blue-500"
              placeholder="Например: труба ПВХ 50мм, 2 шт; кран шаровый ½"
              value={text}
              onChange={e => setText(e.target.value)}
              autoFocus
            />
          </div>
        )}

        {targetStatus === 'Уточнение' && (
          <div>
            <p className="text-sm text-gray-600 mb-2">Введите вопрос для жителя:</p>
            <textarea
              className="w-full border rounded-xl p-3 text-sm min-h-[100px] focus:outline-none focus:border-blue-500"
              placeholder="Например: Укажите точный адрес и этаж"
              value={text}
              onChange={e => setText(e.target.value)}
              autoFocus
            />
          </div>
        )}

        {targetStatus === 'Выполнена' && (
          <div>
            <p className="text-sm text-gray-600 mb-2">Опишите что было сделано:</p>
            <textarea
              className="w-full border rounded-xl p-3 text-sm min-h-[120px] focus:outline-none focus:border-blue-500"
              placeholder="Например: Заменён смеситель на кухне, протечка устранена"
              value={text}
              onChange={e => setText(e.target.value)}
              autoFocus
            />
          </div>
        )}

        <div className="flex gap-2 mt-4">
          <button
            onClick={onCancel}
            className="flex-1 border py-2 rounded-xl text-sm text-gray-600 hover:bg-gray-50"
          >
            Отмена
          </button>
          <button
            onClick={handleConfirm}
            disabled={!isValid()}
            className="flex-1 bg-blue-600 text-white py-2 rounded-xl text-sm font-medium disabled:opacity-40"
          >
            Подтвердить
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Modify KanbanBoard.tsx to intercept drag and show modal**

The key change: instead of calling API directly in `handleDragEnd`, store the pending transition and show `TransitionModal`. Only call the API when user confirms.

```typescript
// frontend/src/components/kanban/KanbanBoard.tsx
import { useState } from 'react'
import {
  DndContext, type DragEndEvent, type DragStartEvent,
  closestCenter, PointerSensor, useSensor, useSensors,
} from '@dnd-kit/core'
import { useKanban, type KanbanColumn as TColumn } from '../../hooks/useKanban'
import KanbanColumn from './KanbanColumn'
import TransitionModal, { type TransitionData } from './TransitionModal'
import { apiClient } from '../../api/client'
import { useQueryClient } from '@tanstack/react-query'

// Statuses that require a modal before transitioning
const MODAL_STATUSES = new Set(['В работе', 'Закуп', 'Уточнение', 'Выполнена', 'Исполнено'])

interface PendingTransition {
  requestNumber: string
  newStatus: string
}

interface Props {
  onCardClick: (requestNumber: string) => void
}

const KANBAN_STATUSES = new Set([
  'Новая', 'В работе', 'Закуп', 'Уточнение',
  'Выполнена', 'Исполнено', 'Принято', 'Отменена',
])
const FROZEN_STATUSES = new Set(['Принято', 'Отменена'])

function resolveTargetStatus(overId: string, columns: TColumn[]): string | null {
  if (KANBAN_STATUSES.has(overId)) return overId
  const col = columns.find(c => c.requests.some(r => r.request_number === overId))
  return col?.status ?? null
}

function isTransitionAllowed(sourceStatus: string | undefined, targetStatus: string): boolean {
  if (!sourceStatus) return false
  if (sourceStatus === targetStatus) return false
  if (FROZEN_STATUSES.has(sourceStatus)) return false
  if (FROZEN_STATUSES.has(targetStatus)) return false
  if (targetStatus === 'Новая' && sourceStatus !== 'Новая') return false
  // Enforce: Выполнена → Исполнено (only), Исполнено → Принято (only)
  if (sourceStatus === 'Выполнена' && targetStatus !== 'Исполнено') return false
  if (sourceStatus === 'Исполнено' && targetStatus !== 'Принято') return false
  return true
}

export { isTransitionAllowed, FROZEN_STATUSES }

export default function KanbanBoard({ onCardClick }: Props) {
  const { columns, isLoading } = useKanban()
  const queryClient = useQueryClient()
  const [activeDragStatus, setActiveDragStatus] = useState<string | null>(null)
  const [pendingTransition, setPendingTransition] = useState<PendingTransition | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  )

  const handleDragStart = (event: DragStartEvent) => {
    const requestNumber = String(event.active.id)
    const sourceCol = columns.find(col =>
      col.requests.some(r => r.request_number === requestNumber),
    )
    setActiveDragStatus(sourceCol?.status ?? null)
  }

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    setActiveDragStatus(null)
    if (!over || active.id === over.id) return

    const requestNumber = String(active.id)
    const newStatus = resolveTargetStatus(String(over.id), columns)
    if (!newStatus) return

    const sourceCol = columns.find(col =>
      col.requests.some(r => r.request_number === requestNumber),
    )
    if (!sourceCol) return
    if (!isTransitionAllowed(sourceCol.status, newStatus)) return

    if (MODAL_STATUSES.has(newStatus)) {
      // Show modal first, wait for user to confirm
      setPendingTransition({ requestNumber, newStatus })
    } else {
      // Direct transition (e.g. Новая → no modal needed)
      commitTransition(requestNumber, { status: newStatus })
    }
  }

  const commitTransition = async (requestNumber: string, data: TransitionData) => {
    // Optimistic update
    queryClient.setQueryData(
      ['kanban', {}],
      (old: { columns: typeof columns } | undefined) => {
        if (!old) return old
        const card = old.columns.flatMap(c => c.requests).find(r => r.request_number === requestNumber)
        if (!card) return old
        const newStatus = data.status
        return {
          columns: old.columns.map((col) => ({
            ...col,
            requests:
              col.status === newStatus
                ? [...col.requests, { ...card, status: newStatus }]
                : col.requests.filter(r => r.request_number !== requestNumber),
            count:
              col.status === newStatus ? col.count + 1
                : col.requests.some(r => r.request_number === requestNumber) ? col.count - 1
                : col.count,
          })),
        }
      },
    )

    try {
      await apiClient.patch(`/api/v2/requests/${requestNumber}`, data)
    } catch {
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
    }
  }

  const handleTransitionConfirm = (data: TransitionData) => {
    if (pendingTransition) {
      commitTransition(pendingTransition.requestNumber, data)
      setPendingTransition(null)
    }
  }

  if (isLoading) {
    return <div className="p-8 text-center text-gray-400">Загрузка...</div>
  }

  return (
    <>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      >
        <div className="flex gap-3 overflow-x-auto pb-4 h-full">
          {columns.map((col) => (
            <KanbanColumn
              key={col.status}
              column={col}
              onCardClick={onCardClick}
              activeDragStatus={activeDragStatus}
            />
          ))}
        </div>
      </DndContext>

      {pendingTransition && (
        <TransitionModal
          requestNumber={pendingTransition.requestNumber}
          targetStatus={pendingTransition.newStatus}
          onConfirm={handleTransitionConfirm}
          onCancel={() => setPendingTransition(null)}
        />
      )}
    </>
  )
}
```

- [ ] **Step 3: Manual test**

```bash
# Open http://localhost:3002/dashboard
# Drag a card to "В работе" → modal should appear with employee list
# Select "Дежурный" → click Подтвердить → card moves to В работе
# Drag a card to "Закуп" → modal should appear with textarea
# Type "Труба ПВХ 50мм" → confirm → card moves to Закуп
# Try dragging from "Принято" → should not move (frozen)
# Try dragging "Выполнена" card to "Закуп" → should not move (state machine)
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/kanban/TransitionModal.tsx frontend/src/components/kanban/KanbanBoard.tsx
git commit -m "feat: kanban status transition modals with mandatory fields"
```

---

## Chunk 3: RequestDetailModal — Add Actions

### Task 4: Make RequestDetailModal interactive

**Context:** `RequestDetailModal.tsx` is fully read-only. Needs: action buttons based on status, manager confirmation for "Выполнена" → "Исполнено", display of completion report/photo, status history (comments as audit trail).

**Files:**
- Modify: `frontend/src/components/kanban/RequestDetailModal.tsx`

- [ ] **Step 1: Rewrite RequestDetailModal with action buttons**

Replace the entire file content:

```typescript
// frontend/src/components/kanban/RequestDetailModal.tsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../../api/client'

const URGENCY_COLOR: Record<string, string> = {
  'Обычная': 'bg-green-100 text-green-700',
  'Средняя': 'bg-yellow-100 text-yellow-700',
  'Срочная': 'bg-orange-100 text-orange-700',
  'Критическая': 'bg-red-100 text-red-700',
}

const SOURCE_ICON: Record<string, string> = {
  bot: '🤖', twa: '📱', web: '🌐', call_center: '📞',
}

interface Props {
  requestNumber: string | null
  onClose: () => void
}

export default function RequestDetailModal({ requestNumber, onClose }: Props) {
  const queryClient = useQueryClient()
  const [comment, setComment] = useState('')
  const [confirmNote, setConfirmNote] = useState('')
  const [showConfirmSection, setShowConfirmSection] = useState(false)

  const { data: request } = useQuery({
    queryKey: ['request', requestNumber],
    queryFn: () => apiClient.get(`/api/v2/requests/${requestNumber}`).then(r => r.data),
    enabled: !!requestNumber,
  })

  const { data: comments } = useQuery({
    queryKey: ['comments', requestNumber],
    queryFn: () => apiClient.get(`/api/v2/requests/${requestNumber}/comments`).then(r => r.data),
    enabled: !!requestNumber,
  })

  const updateRequest = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      apiClient.patch(`/api/v2/requests/${requestNumber}`, data).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['request', requestNumber] })
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
      setShowConfirmSection(false)
      setConfirmNote('')
    },
  })

  const postComment = useMutation({
    mutationFn: (text: string) =>
      apiClient.post(`/api/v2/requests/${requestNumber}/comments`, { text, is_internal: true }).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comments', requestNumber] })
      setComment('')
    },
  })

  if (!requestNumber) return null

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white rounded-2xl w-full max-w-lg max-h-[85vh] shadow-xl flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {!request ? (
          <div className="p-6 text-gray-400 text-center">Загрузка...</div>
        ) : (
          <>
            {/* Header */}
            <div className="p-4 border-b flex justify-between items-start shrink-0">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-gray-500">{request.request_number}</span>
                  <span className="text-sm">{SOURCE_ICON[request.source ?? ''] ?? ''}</span>
                </div>
                <h2 className="font-bold mt-1">{request.category}</h2>
              </div>
              <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
            </div>

            {/* Body */}
            <div className="p-4 overflow-y-auto flex-1 space-y-4">
              {/* Badges */}
              <div className="flex gap-2 flex-wrap">
                <span className="text-xs px-2 py-1 rounded-full bg-blue-100 text-blue-700">{request.status}</span>
                {request.urgency && (
                  <span className={`text-xs px-2 py-1 rounded-full ${URGENCY_COLOR[request.urgency] ?? 'bg-gray-100 text-gray-600'}`}>
                    {request.urgency}
                  </span>
                )}
                {request.manager_confirmed && (
                  <span className="text-xs px-2 py-1 rounded-full bg-emerald-100 text-emerald-700">✓ Подтверждено</span>
                )}
              </div>

              {/* Description */}
              {request.description && (
                <p className="text-sm text-gray-700">{request.description}</p>
              )}

              {/* Details grid */}
              <div className="text-xs text-gray-500 space-y-1">
                <div>Создана: {new Date(request.created_at).toLocaleString('ru')}</div>
                {request.executor_name && <div>Исполнитель: <span className="font-medium text-gray-700">{request.executor_name}</span></div>}
                {request.address && <div>Адрес: {request.address}</div>}
                {request.requested_materials && (
                  <div className="bg-amber-50 border border-amber-200 rounded-lg p-2 mt-1">
                    <span className="font-semibold text-amber-700">Закуп:</span>{' '}
                    <span className="text-amber-800">{request.requested_materials}</span>
                  </div>
                )}
                {request.completion_report && (
                  <div className="bg-green-50 border border-green-200 rounded-lg p-2 mt-1">
                    <span className="font-semibold text-green-700">Отчёт:</span>{' '}
                    <span className="text-green-800">{request.completion_report}</span>
                  </div>
                )}
                {request.notes && (
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-2 mt-1">
                    <span className="font-semibold text-blue-700">Уточнение:</span>{' '}
                    <span className="text-blue-800">{request.notes}</span>
                  </div>
                )}
              </div>

              {/* Manager confirmation section (shown when status = Выполнена) */}
              {request.status === 'Выполнена' && !request.manager_confirmed && (
                <div className="border border-gray-200 rounded-xl p-3 bg-gray-50">
                  {!showConfirmSection ? (
                    <button
                      onClick={() => setShowConfirmSection(true)}
                      className="w-full bg-emerald-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-emerald-700"
                    >
                      ✓ Подтвердить и отправить жителю
                    </button>
                  ) : (
                    <div className="space-y-2">
                      <p className="text-xs text-gray-600">Комментарий к подтверждению (необязательно):</p>
                      <textarea
                        className="w-full border rounded-lg p-2 text-sm min-h-[60px]"
                        placeholder="Всё выполнено качественно"
                        value={confirmNote}
                        onChange={e => setConfirmNote(e.target.value)}
                      />
                      <div className="flex gap-2">
                        <button
                          onClick={() => setShowConfirmSection(false)}
                          className="flex-1 border py-1.5 rounded-lg text-sm text-gray-600"
                        >
                          Отмена
                        </button>
                        <button
                          onClick={() => updateRequest.mutate({
                            status: 'Исполнено',
                            manager_confirmed: true,
                            ...(confirmNote ? { manager_confirmation_notes: confirmNote } : {}),
                          })}
                          disabled={updateRequest.isPending}
                          className="flex-1 bg-emerald-600 text-white py-1.5 rounded-lg text-sm font-medium disabled:opacity-50"
                        >
                          {updateRequest.isPending ? 'Сохраняю...' : 'Подтвердить'}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Comments / history */}
              {comments && comments.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">История</h3>
                  <div className="space-y-2">
                    {comments.map((c: { id: number; comment_text: string; comment_type: string; is_internal: boolean; created_at: string }) => (
                      <div key={c.id} className={`rounded-xl p-3 border text-sm ${c.is_internal ? 'bg-amber-50 border-amber-100' : 'bg-gray-50'}`}>
                        <p>{c.comment_text}</p>
                        <span className="text-xs text-gray-400">{new Date(c.created_at).toLocaleString('ru')}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Add internal comment */}
              <div className="space-y-2">
                <h3 className="text-xs font-semibold text-gray-500 uppercase">Комментарий менеджера</h3>
                <div className="flex gap-2">
                  <input
                    className="flex-1 border rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
                    placeholder="Добавить заметку..."
                    value={comment}
                    onChange={e => setComment(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && comment.trim() && postComment.mutate(comment)}
                  />
                  <button
                    onClick={() => postComment.mutate(comment)}
                    disabled={!comment.trim() || postComment.isPending}
                    className="bg-blue-600 text-white px-3 py-2 rounded-xl text-sm disabled:opacity-40"
                  >
                    ↑
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Manual test**

```bash
# Open Kanban page, click a card
# Verify: badges, description, address, executor_name shown
# Move a card to "Выполнена" via drag (after Task 3 is done)
# Click that card → "Подтвердить и отправить жителю" button should appear
# Click it → confirm → status should change to "Исполнено"
# Add a comment → appears in history
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/kanban/RequestDetailModal.tsx
git commit -m "feat: RequestDetailModal — add manager actions, confirmation, comment input"
```

---

## Chunk 4: TWA Fixes

### Task 5: Fix TWA accept/return flow

**Context:** `TWARequestDetailPage.tsx` — `handleAccept` doesn't send rating; `handleReturn` doesn't send `return_reason` (mandatory). Need to fix both.

**Files:**
- Modify: `frontend/src/pages/twa/TWARequestDetailPage.tsx`

- [ ] **Step 1: Fix handleAccept to send rating + fix handleReturn to require reason**

Replace the acceptance block and handlers (lines 40-49 and 110-130):

```typescript
// New state: add returnReason
const [returnReason, setReturnReason] = useState('')
const [showReturnForm, setShowReturnForm] = useState(false)

const handleAccept = async () => {
  const payload: Record<string, unknown> = { status: 'Принято' }
  if (rating > 0) payload.rating = rating   // send if set
  await apiClient.patch(`/api/v2/requests/${number}`, payload)
  queryClient.invalidateQueries({ queryKey: ['request', number] })
  navigate('/twa')
}

const handleReturn = async () => {
  if (!returnReason.trim()) return
  await apiClient.patch(`/api/v2/requests/${number}`, {
    status: 'В работе',
    return_reason: returnReason.trim(),
  })
  queryClient.invalidateQueries({ queryKey: ['request', number] })
  navigate('/twa')
}

// Replace acceptance block JSX (lines 110-130):
{showAcceptance && (
  <div className="bg-white border-t p-4">
    {!showReturnForm ? (
      <>
        <p className="font-medium mb-2">Оцените работу (необязательно)</p>
        <div className="flex gap-2 mb-3">
          {[1,2,3,4,5].map(n => (
            <button key={n} onClick={() => setRating(prev => prev === n ? 0 : n)}
              className={`text-2xl ${n <= rating ? 'text-yellow-400' : 'text-gray-300'}`}>
              &#9733;
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowReturnForm(true)} className="flex-1 border py-2 rounded-xl text-sm">
            &#8617; Вернуть
          </button>
          <button onClick={handleAccept} className="flex-1 bg-blue-600 text-white py-2 rounded-xl text-sm">
            &#10003; Принять
          </button>
        </div>
      </>
    ) : (
      <>
        <p className="font-medium mb-2">Почему возвращаете?</p>
        <textarea
          className="w-full border rounded-xl p-3 text-sm min-h-[80px] mb-3"
          placeholder="Опишите что не так..."
          value={returnReason}
          onChange={e => setReturnReason(e.target.value)}
          autoFocus
        />
        <div className="flex gap-2">
          <button onClick={() => setShowReturnForm(false)} className="flex-1 border py-2 rounded-xl text-sm">
            Назад
          </button>
          <button
            onClick={handleReturn}
            disabled={!returnReason.trim()}
            className="flex-1 bg-red-500 text-white py-2 rounded-xl text-sm disabled:opacity-40"
          >
            Отправить
          </button>
        </div>
      </>
    )}
  </div>
)}
```

- [ ] **Step 2: Add address field to TWA create (step 2)**

In `frontend/src/pages/twa/TWACreatePage.tsx`, add address input in step 2 (after description textarea, before the "Далее" button):

```typescript
// After the description textarea, add:
<p className="text-sm font-medium mt-4">Адрес (квартира/подъезд):</p>
<input
  className="w-full border rounded-xl p-3 text-sm"
  placeholder="Например: кв. 42, подъезд 3"
  value={form.address}
  onChange={(e) => setForm({ ...form, address: e.target.value })}
/>
```

Also show address in step 3 review:

```typescript
// In step 3 summary block, after description:
{form.address && (
  <>
    <p className="text-xs text-gray-400 mb-1 mt-2">Адрес</p>
    <p className="text-sm">{form.address}</p>
  </>
)}
```

- [ ] **Step 3: Manual test**

```bash
# Open http://localhost:3002/twa
# Create a request — step 2 should have address field
# Navigate to a request in "Исполнено" status
# Click "Вернуть" → return form with reason text should appear
# Fill reason → "Отправить" → request should go to "В работе"
# Accept → rating is optional, accept works without rating
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/twa/TWARequestDetailPage.tsx frontend/src/pages/twa/TWACreatePage.tsx
git commit -m "feat: TWA — fix accept/return flow, add address field to create"
```

---

## Chunk 5: CallCenter Fixes

### Task 6: Fix CallCenter modal — address + categories + error handling

**Context:** `CallCenterModal.tsx` — no address field (mandatory), only 6 categories (should be 10 matching TWA), no error handling on submit.

**Files:**
- Modify: `frontend/src/components/callcenter/CallCenterModal.tsx`

- [ ] **Step 1: Rewrite CallCenterModal with fixes**

```typescript
// frontend/src/components/callcenter/CallCenterModal.tsx
import { useState, useEffect } from 'react'
import { apiClient } from '../../api/client'
import { useQueryClient } from '@tanstack/react-query'

interface Props { isOpen: boolean; onClose: () => void }

// Synced with TWACreatePage.tsx CATEGORIES (10 items)
const CATEGORIES = [
  'Электрика', 'Сантехника', 'Отопление', 'Вентиляция',
  'Лифт', 'Уборка', 'Благоустройство', 'Безопасность',
  'Интернет/ТВ', 'Другое',
]

const INITIAL_FORM = { category: '', urgency: 'Обычная', description: '', address: '' }

export default function CallCenterModal({ isOpen, onClose }: Props) {
  const [query, setQuery] = useState('')
  const [residents, setResidents] = useState<Array<{ id: number; full_name: string; phone: string }>>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [form, setForm] = useState(INITIAL_FORM)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const queryClient = useQueryClient()

  useEffect(() => {
    if (isOpen) {
      setQuery('')
      setResidents([])
      setSelected(null)
      setForm(INITIAL_FORM)
      setError('')
    }
  }, [isOpen])

  const search = async () => {
    try {
      const { data } = await apiClient.get('/api/v2/callcenter/search-resident', { params: { q: query } })
      setResidents(data)
    } catch {
      setError('Ошибка поиска жителя')
    }
  }

  const submit = async () => {
    if (!form.address.trim()) {
      setError('Укажите адрес')
      return
    }
    setLoading(true)
    setError('')
    try {
      await apiClient.post('/api/v2/callcenter/requests', {
        ...form,
        user_id: selected || undefined,
      })
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
      onClose()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Ошибка при создании заявки')
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) return null
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-xl max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-bold">Создание заявки по звонку</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
        </div>

        {/* Resident search */}
        <div className="flex gap-2 mb-3">
          <input
            className="flex-1 border rounded-lg px-3 py-2 text-sm"
            placeholder="Телефон или ФИО жителя"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search()}
          />
          <button onClick={search} className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm">Найти</button>
        </div>

        {residents.length > 0 && (
          <div className="mb-3 space-y-1">
            {residents.map((r) => (
              <div key={r.id} onClick={() => setSelected(r.id)}
                className={`border rounded-lg p-2 cursor-pointer text-sm ${selected === r.id ? 'border-blue-500 bg-blue-50' : 'hover:bg-gray-50'}`}>
                <span className="font-medium">{r.full_name}</span> &middot; {r.phone}
              </div>
            ))}
          </div>
        )}

        {/* Category */}
        <select className="w-full border rounded-lg px-3 py-2 text-sm mb-2"
          value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
          <option value="">Категория...</option>
          {CATEGORIES.map(c => <option key={c}>{c}</option>)}
        </select>

        {/* Urgency */}
        <select className="w-full border rounded-lg px-3 py-2 text-sm mb-2"
          value={form.urgency} onChange={(e) => setForm({ ...form, urgency: e.target.value })}>
          {['Обычная', 'Средняя', 'Срочная', 'Критическая'].map(u => <option key={u}>{u}</option>)}
        </select>

        {/* Description */}
        <textarea className="w-full border rounded-lg px-3 py-2 text-sm mb-2" rows={3}
          placeholder="Описание проблемы"
          value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />

        {/* Address (required) */}
        <input
          className="w-full border rounded-lg px-3 py-2 text-sm mb-4"
          placeholder="Адрес / квартира *"
          value={form.address}
          onChange={(e) => setForm({ ...form, address: e.target.value })}
        />

        {error && <p className="text-red-500 text-sm mb-3">{error}</p>}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm border rounded-lg">Отмена</button>
          <button
            onClick={submit}
            disabled={loading || !form.category || !form.description || !form.address.trim()}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg disabled:opacity-50"
          >
            {loading ? 'Создаю...' : 'Создать заявку'}
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Manual test**

```bash
# Open Kanban page → click "Создать по звонку"
# Try to submit without address → should show error "Укажите адрес"
# Verify 10 categories in dropdown (same as TWA)
# Submit with all fields → card appears in Kanban "Новая"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/callcenter/CallCenterModal.tsx
git commit -m "feat: callcenter — add address field, sync 10 categories, add error handling"
```

---

## Chunk 6: Employee Block/Assign

### Task 7: Wire up employee Assign and Block buttons

**Context:** `StaffCard.tsx` has `onAssign` and `onBlock` props but `EmployeesPage.tsx` passes `<StaffCard employee={emp} />` without handlers. Need to: add `useBlockEmployee`/`useUnblockEmployee` hooks, add `AssignRequestModal` for selecting a request, wire everything up.

**Files:**
- Modify: `frontend/src/hooks/useEmployees.ts`
- Create: `frontend/src/components/employees/AssignRequestModal.tsx`
- Modify: `frontend/src/pages/EmployeesPage.tsx`
- Modify: `frontend/src/components/employees/StaffCard.tsx` (expose `status` field for blocked state)

- [ ] **Step 1: Add block/unblock hooks to useEmployees.ts**

Append to `frontend/src/hooks/useEmployees.ts`:

```typescript
export function useBlockEmployee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.patch(`/api/v2/shifts/employees/${id}/block`).then(r => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['employees'] }),
    onError: (error) => console.error('Block employee failed:', error),
  })
}

export function useUnblockEmployee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.patch(`/api/v2/shifts/employees/${id}/unblock`).then(r => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['employees'] }),
    onError: (error) => console.error('Unblock employee failed:', error),
  })
}
```

- [ ] **Step 2: Create AssignRequestModal.tsx**

```typescript
// frontend/src/components/employees/AssignRequestModal.tsx
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../../api/client'
import type { EmployeeBrief } from '../../hooks/useEmployees'

interface Props {
  employee: EmployeeBrief
  onClose: () => void
}

export default function AssignRequestModal({ employee, onClose }: Props) {
  const queryClient = useQueryClient()
  const name = [employee.first_name, employee.last_name].filter(Boolean).join(' ') || `#${employee.id}`

  const { data: requests = [] } = useQuery({
    queryKey: ['requests', 'assignable'],
    queryFn: () =>
      apiClient.get('/api/v2/requests', { params: { status: 'В работе', limit: 50 } }).then(r => r.data),
  })

  const assign = useMutation({
    mutationFn: (requestNumber: string) =>
      apiClient.patch(`/api/v2/requests/${requestNumber}`, { executor_id: employee.id }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
      queryClient.invalidateQueries({ queryKey: ['requests', 'assignable'] })
      onClose()
    },
  })

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]" onClick={onClose}>
      <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()}>
        <h3 className="font-bold text-lg mb-1">Назначить заявку</h3>
        <p className="text-sm text-gray-500 mb-4">Исполнитель: {name}</p>

        {requests.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-4">Нет заявок "В работе" без исполнителя</p>
        ) : (
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {requests.map((req: { request_number: string; category: string; address?: string; urgency?: string }) => (
              <button
                key={req.request_number}
                onClick={() => assign.mutate(req.request_number)}
                disabled={assign.isPending}
                className="w-full text-left border rounded-xl p-3 hover:bg-gray-50 transition-colors"
              >
                <div className="flex justify-between items-start">
                  <span className="font-mono text-xs text-gray-400">{req.request_number}</span>
                  {req.urgency && <span className="text-xs text-gray-500">{req.urgency}</span>}
                </div>
                <p className="text-sm font-medium">{req.category}</p>
                {req.address && <p className="text-xs text-gray-400">{req.address}</p>}
              </button>
            ))}
          </div>
        )}

        <button onClick={onClose} className="w-full mt-4 border py-2 rounded-xl text-sm text-gray-600 hover:bg-gray-50">
          Закрыть
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Add `status` to EmployeeBrief type**

In `frontend/src/types/api.ts` (or wherever `EmployeeBrief` is defined), add `status?: string`. Check the file first:

```bash
grep -n "EmployeeBrief" /path/to/frontend/src/types/api.ts
```

Add `status?: string` to the interface.

- [ ] **Step 4: Wire up buttons in EmployeesPage.tsx**

In `frontend/src/pages/EmployeesPage.tsx`:

```typescript
// Add imports
import { useBlockEmployee, useUnblockEmployee } from '../hooks/useEmployees'
import AssignRequestModal from '../components/employees/AssignRequestModal'
import type { EmployeeBrief } from '../hooks/useEmployees'

// Inside the component, add state and hooks:
const [assignEmployee, setAssignEmployee] = useState<EmployeeBrief | null>(null)
const blockEmployee = useBlockEmployee()
const unblockEmployee = useUnblockEmployee()

const handleAssign = (employee: EmployeeBrief) => {
  setAssignEmployee(employee)
}

const handleBlock = (employee: EmployeeBrief) => {
  const isBlocked = employee.status === 'blocked'
  if (isBlocked) {
    if (confirm(`Разблокировать ${[employee.first_name, employee.last_name].filter(Boolean).join(' ')}?`)) {
      unblockEmployee.mutate(employee.id)
    }
  } else {
    if (confirm(`Заблокировать ${[employee.first_name, employee.last_name].filter(Boolean).join(' ')}? Сотрудник потеряет доступ.`)) {
      blockEmployee.mutate(employee.id)
    }
  }
}

// Update StaffCard rendering (line 238) to pass handlers:
{employees.map(emp => (
  <StaffCard
    key={emp.id}
    employee={emp}
    onAssign={handleAssign}
    onBlock={handleBlock}
  />
))}

// Add modal at end of JSX, before closing </div>:
{assignEmployee && (
  <AssignRequestModal
    employee={assignEmployee}
    onClose={() => setAssignEmployee(null)}
  />
)}
```

- [ ] **Step 5: Update StaffCard to show blocked state**

In `StaffCard.tsx`, update the "Блок" button text based on employee status:

```typescript
// Change the Блок button (line 221-234) to:
<button
  onClick={() => onBlock?.(employee)}
  style={{
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    fontSize: '12px',
    color: employee.status === 'blocked' ? 'var(--text-muted)' : 'var(--red)',
    padding: '6px 8px',
    fontFamily: 'var(--font-display)',
  }}
>
  {employee.status === 'blocked' ? 'Разблок' : 'Блок'}
</button>
```

Also add `status?: string` to the `EmployeeBrief` usage — the backend already returns it via `EmployeeBrief` schema (need to expose it). Add to `uk_management_bot/api/shifts/schemas.py`:

```python
class EmployeeBrief(BaseModel):
    id: int
    first_name: Optional[str]
    last_name: Optional[str]
    phone: Optional[str]
    specialization: list[str]
    active_shift_id: Optional[int]
    verification_status: str
    status: str = "approved"    # ← add: approved | blocked | pending
    ...
```

And in the `_coerce_from_orm` validator, add:
```python
"status": getattr(values, "status", "approved"),
```

- [ ] **Step 6: Restart API + manual test**

```bash
docker compose restart api
# Open Employees page
# Find a verified employee → click "Блок" → confirm → button should change to "Разблок"
# Click "Разблок" → confirm → button back to "Блок"
# Click "Назначить" → modal with "В работе" requests opens
# Select a request → it gets assigned to this employee
```

- [ ] **Step 7: Commit**

```bash
git add \
  frontend/src/hooks/useEmployees.ts \
  frontend/src/components/employees/AssignRequestModal.tsx \
  frontend/src/pages/EmployeesPage.tsx \
  frontend/src/components/employees/StaffCard.tsx \
  uk_management_bot/api/shifts/schemas.py
git commit -m "feat: employees — wire up assign/block buttons, add block/unblock API"
```

---

## Final Step: Rebuild Frontend

After all tasks complete, rebuild the frontend Docker image to deploy changes:

```bash
docker compose build frontend && docker compose up -d frontend
echo "Frontend deployed. Open http://localhost:3002"
```
