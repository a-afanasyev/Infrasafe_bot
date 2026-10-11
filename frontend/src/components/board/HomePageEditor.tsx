import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ExternalLink } from 'lucide-react'
import type { HomeBlockCfg, HomeBlockId, HomeCfg, LocalizedText } from '../../types/boardConfig'
import { HOME_BLOCK_IDS } from '../../types/boardConfig'
import { blockModuleEnabled } from '../home/homeConfig'
import LocalizedField from './LocalizedField'

interface HomePageEditorProps {
  home: HomeCfg
  onChange: (home: HomeCfg) => void
}

// Где менеджер управляет данными блока, если они живут не в этом редакторе.
const MANAGE_LINKS: Partial<Record<HomeBlockId, string>> = {
  requests: '/dashboard',
  elevators: '/dashboard/elevators',
  workreports: '/dashboard/work-reports',
}

const EMPTY: LocalizedText = { ru: '', uz: '' }

// Раздел «Страница жителей» редактора витрины: тексты страницы и блоки — у
// каждого видимость, свой заголовок, откуда берутся данные и где ими управлять.
// Каждая правка отдаёт НОВЫЙ объект — черновик редактора не мутируется.
export default function HomePageEditor({ home, onChange }: HomePageEditorProps) {
  const { t } = useTranslation()
  const byId = new Map(home.blocks.map((b) => [b.id, b]))

  const setText = (field: 'complex_name' | 'title' | 'eyebrow' | 'tagline', value: LocalizedText) =>
    onChange({ ...home, [field]: value })

  const setBlock = (id: HomeBlockId, patch: Partial<HomeBlockCfg>) =>
    onChange({
      ...home,
      blocks: home.blocks.map((b) => (b.id === id ? { ...b, ...patch } : b)),
    })

  return (
    <>
      <p className="text-xs text-text-muted">{t('boardEditor.homeHint')}</p>
      <Link to="/home" target="_blank" className="inline-flex items-center gap-1 self-start text-xs font-semibold text-accent hover:underline">
        {t('boardEditor.homeOpen')} <ExternalLink size={12} />
      </Link>
      <LocalizedField label={t('boardEditor.homeComplexName')} value={home.complex_name} onChange={(v) => setText('complex_name', v)} />
      <LocalizedField label={t('boardEditor.homeTitle')} value={home.title} onChange={(v) => setText('title', v)} />
      <LocalizedField label={t('boardEditor.homeEyebrow')} value={home.eyebrow} onChange={(v) => setText('eyebrow', v)} />
      <LocalizedField label={t('boardEditor.homeTagline')} value={home.tagline} onChange={(v) => setText('tagline', v)} />

      <div className="mt-1 text-xs font-bold text-text-primary">{t('boardEditor.homeBlocks')}</div>
      <p className="text-xs text-text-muted">{t('boardEditor.homeBlocksHint')}</p>
      {HOME_BLOCK_IDS.map((id) => {
        const block = byId.get(id)
        // Блока нет в черновике — бэкенд вырезал его флагом модуля (или выключен
        // фронтовый флаг): настраивать нечего, но показываем, что он существует.
        const available = block !== undefined && blockModuleEnabled(id)
        const manage = MANAGE_LINKS[id]
        return (
          <div key={id} data-testid={`home-block-${id}`} className="rounded-sm border border-border-default bg-bg-surface p-3">
            <label className="mb-1 flex items-center gap-2 text-sm font-semibold text-text-primary">
              <input
                type="checkbox"
                checked={available && block.visible}
                disabled={!available}
                onChange={() => block && setBlock(id, { visible: !block.visible })}
              />
              {t(`boardEditor.blocks.${id}`)}
            </label>
            <p className="mb-2 text-xs text-text-muted">
              {available ? t(`boardEditor.blockSources.${id}`) : t('boardEditor.homeModuleOff')}
              {available && manage && (
                <>
                  {' '}
                  <Link to={manage} className="font-semibold text-accent hover:underline">
                    {t(`boardEditor.manageIn.${id}`)} →
                  </Link>
                </>
              )}
            </p>
            {available && (
              <LocalizedField
                label={t('boardEditor.homeBlockTitle')}
                value={block.title ?? EMPTY}
                onChange={(v) => setBlock(id, { title: v })}
              />
            )}
          </div>
        )
      })}
    </>
  )
}
