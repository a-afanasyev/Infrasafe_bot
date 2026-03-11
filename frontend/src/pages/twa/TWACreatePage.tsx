import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiClient } from '../../api/client'
import { useTWAAuth } from '../../hooks/useTWAAuth'

const CATEGORIES = ['Электрика', 'Сантехника', 'Отопление', 'Вентиляция', 'Лифт', 'Уборка', 'Благоустройство', 'Безопасность', 'Интернет/ТВ', 'Другое']
const URGENCIES = ['Обычная', 'Средняя', 'Срочная', 'Критическая']

export default function TWACreatePage() {
  useTWAAuth()
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [form, setForm] = useState({
    category: '',
    urgency: 'Обычная',
    description: '',
    address: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    setLoading(true)
    setError('')
    try {
      await apiClient.post('/api/v2/requests', {
        ...form,
        source: 'twa',
      })
      navigate('/twa')
    } catch {
      setError('Ошибка при создании заявки')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-4 bg-gray-50 min-h-screen">
      <div className="flex items-center gap-2 mb-4">
        <button onClick={() => step > 1 ? setStep(step - 1) : navigate('/twa')} className="text-blue-600 text-sm">
          &larr; Назад
        </button>
        <h1 className="text-lg font-bold">Новая заявка</h1>
        <span className="ml-auto text-xs text-gray-400">Шаг {step}/3</span>
      </div>

      {step === 1 && (
        <div className="space-y-2">
          <p className="text-sm font-medium mb-2">Выберите категорию:</p>
          {CATEGORIES.map(c => (
            <button key={c} onClick={() => { setForm({ ...form, category: c }); setStep(2) }}
              className={`w-full text-left border rounded-xl p-3 text-sm ${form.category === c ? 'border-blue-500 bg-blue-50' : 'bg-white'}`}>
              {c}
            </button>
          ))}
        </div>
      )}

      {step === 2 && (
        <div className="space-y-3">
          <p className="text-sm font-medium">Срочность:</p>
          <div className="flex gap-2 flex-wrap">
            {URGENCIES.map(u => (
              <button key={u} onClick={() => setForm({ ...form, urgency: u })}
                className={`px-3 py-1.5 rounded-full text-sm border ${form.urgency === u ? 'border-blue-500 bg-blue-50 text-blue-700' : 'bg-white'}`}>
                {u}
              </button>
            ))}
          </div>

          <p className="text-sm font-medium mt-4">Описание проблемы:</p>
          <textarea
            className="w-full border rounded-xl p-3 text-sm min-h-[120px]"
            placeholder="Опишите проблему подробно..."
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />

          <p className="text-sm font-medium mt-4">Адрес (квартира/подъезд):</p>
          <input
            className="w-full border rounded-xl p-3 text-sm"
            placeholder="Например: кв. 42, подъезд 3"
            value={form.address}
            onChange={(e) => setForm({ ...form, address: e.target.value })}
          />

          <button
            onClick={() => setStep(3)}
            disabled={!form.description}
            className="w-full bg-blue-600 text-white py-3 rounded-xl font-medium disabled:opacity-50">
            Далее
          </button>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-3">
          <div className="bg-white rounded-xl p-4 border">
            <p className="text-xs text-gray-400 mb-1">Категория</p>
            <p className="text-sm font-medium">{form.category}</p>
            <p className="text-xs text-gray-400 mb-1 mt-2">Срочность</p>
            <p className="text-sm">{form.urgency}</p>
            <p className="text-xs text-gray-400 mb-1 mt-2">Описание</p>
            <p className="text-sm">{form.description}</p>
            {form.address && (
              <>
                <p className="text-xs text-gray-400 mb-1 mt-2">Адрес</p>
                <p className="text-sm">{form.address}</p>
              </>
            )}
          </div>

          {error && <p className="text-red-500 text-sm">{error}</p>}

          <button
            onClick={submit}
            disabled={loading}
            className="w-full bg-blue-600 text-white py-3 rounded-xl font-medium disabled:opacity-50">
            {loading ? 'Отправка...' : 'Отправить заявку'}
          </button>
        </div>
      )}
    </div>
  )
}
