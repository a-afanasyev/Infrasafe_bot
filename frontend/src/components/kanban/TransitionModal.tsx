import { useState, useEffect } from 'react'
import { useEmployees } from '../../hooks/useEmployees'

export interface TransitionData {
  status: string
  executor_id?: number
  notes?: string
  requested_materials?: string
  completion_report?: string
}

interface Props {
  requestNumber: string
  targetStatus: string
  onConfirm: (data: TransitionData) => void
  onCancel: () => void
}

export default function TransitionModal({ requestNumber: _requestNumber, targetStatus, onConfirm, onCancel }: Props) {
  const [executorId, setExecutorId] = useState<number | 'duty' | ''>('')
  const [text, setText] = useState('')
  const { data: employees = [] } = useEmployees({ verification_status: 'verified' })

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
    if (targetStatus === 'В работе' && executorId !== 'duty' && executorId !== '') {
      data.executor_id = executorId as number
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
    'Исполнено': 'Подтвердить выполнение',
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
                    {emp.active_shift_id !== null && (
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

        {targetStatus === 'Исполнено' && (
          <p className="text-sm text-gray-600">
            Подтвердить перевод заявки в статус "Исполнено"? Житель получит уведомление для приёмки.
          </p>
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
