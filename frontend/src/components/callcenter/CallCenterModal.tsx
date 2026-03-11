import { useState, useEffect } from 'react'
import { apiClient } from '../../api/client'
import { useQueryClient } from '@tanstack/react-query'

interface Props { isOpen: boolean; onClose: () => void }

// Synced with TWACreatePage.tsx — 10 categories
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
              <div
                key={r.id}
                onClick={() => setSelected(r.id)}
                className={`border rounded-lg p-2 cursor-pointer text-sm ${selected === r.id ? 'border-blue-500 bg-blue-50' : 'hover:bg-gray-50'}`}
              >
                <span className="font-medium">{r.full_name}</span> &middot; {r.phone}
              </div>
            ))}
          </div>
        )}

        {/* Category */}
        <select
          className="w-full border rounded-lg px-3 py-2 text-sm mb-2"
          value={form.category}
          onChange={(e) => setForm({ ...form, category: e.target.value })}
        >
          <option value="">Категория...</option>
          {CATEGORIES.map(c => <option key={c}>{c}</option>)}
        </select>

        {/* Urgency */}
        <select
          className="w-full border rounded-lg px-3 py-2 text-sm mb-2"
          value={form.urgency}
          onChange={(e) => setForm({ ...form, urgency: e.target.value })}
        >
          {['Обычная', 'Средняя', 'Срочная', 'Критическая'].map(u => <option key={u}>{u}</option>)}
        </select>

        {/* Description */}
        <textarea
          className="w-full border rounded-lg px-3 py-2 text-sm mb-2"
          rows={3}
          placeholder="Описание проблемы"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />

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
