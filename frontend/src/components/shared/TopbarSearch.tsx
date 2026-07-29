import { useEffect, useRef } from 'react'
import { Input } from '@/components/ui/input'

interface Props {
  placeholder: string
  onSearch: (value: string) => void
  /** Пауза перед вызовом onSearch, мс. */
  delay?: number
  className?: string
}

/** Поле поиска для топбара: НЕконтролируемое + debounce.
 *
 *  Контролируемому полю в топбаре не место (`docs/bugs-2026-07-28.md`, BUG-2,
 *  найдено в проде): страница отдаёт узел не напрямую, а через состояние
 *  контекста `useTopbar`, обновляемое в useEffect — то есть ВТОРЫМ коммитом.
 *  У контролируемого поля React в фазе обработки события сверяет DOM-значение
 *  с последним отрендеренным `value` (всё ещё старым) и откатывает DOM.
 *  Следующее нажатие попадает в это окно — символ теряется: «админ» → «амн»,
 *  а при медленном вводе не остаётся ничего.
 *
 *  Здесь значением владеет DOM, а React только читает его в onChange, поэтому
 *  откатывать нечего. Побочно снимается второй дефект — запрос на каждое
 *  нажатие клавиши.
 *
 *  Компонент устойчив к пересозданию элемента родителем: `defaultValue`
 *  применяется только при монтировании DOM-узла, а узел переиспользуется при
 *  реконсиляции — набранный текст переживает лишний ререндер страницы.
 */
export default function TopbarSearch({
  placeholder,
  onSearch,
  delay = 300,
  className = 'w-[220px]',
}: Props) {
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  // Колбэк держим в ref: иначе пересоздание onSearch родителем (обычное дело
  // для инлайн-стрелки) заставляло бы перевешивать таймер. Пишем в ref в
  // эффекте, а не в фазе рендера — иначе React Compiler справедливо ругается.
  const latest = useRef(onSearch)
  useEffect(() => { latest.current = onSearch }, [onSearch])

  useEffect(() => () => clearTimeout(timer.current), [])

  return (
    <Input
      type="text"
      placeholder={placeholder}
      defaultValue=""
      onChange={e => {
        const value = e.target.value
        clearTimeout(timer.current)
        timer.current = setTimeout(() => latest.current(value), delay)
      }}
      className={className}
    />
  )
}
