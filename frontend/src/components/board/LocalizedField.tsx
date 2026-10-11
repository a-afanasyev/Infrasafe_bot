import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import type { LocalizedText } from '../../types/boardConfig'

interface LocalizedFieldProps {
  label: string
  value: LocalizedText
  onChange: (v: LocalizedText) => void
  textarea?: boolean
}

// Пара полей RU/UZ редактора витрины.
export default function LocalizedField({ label, value, onChange, textarea }: LocalizedFieldProps) {
  const Field = textarea ? Textarea : Input
  return (
    <div>
      <div className="mb-1 text-xs font-semibold text-text-muted">{label}</div>
      <div className="grid grid-cols-2 gap-2">
        <Field
          value={value.ru}
          placeholder="RU"
          onChange={(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
            onChange({ ...value, ru: e.target.value })
          }
        />
        <Field
          value={value.uz}
          placeholder="UZ"
          onChange={(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
            onChange({ ...value, uz: e.target.value })
          }
        />
      </div>
    </div>
  )
}
