import type { Dispatch, SetStateAction } from 'react'
import { useTranslation } from 'react-i18next'
import type { YardBrief, BuildingBrief, ApartmentBrief } from '../../types/api'
import YardFormModal from './YardFormModal'
import BuildingFormModal from './BuildingFormModal'
import ApartmentFormModal from './ApartmentFormModal'
import AddObjectModal from './AddObjectModal'
import BulkCreateModal from './BulkCreateModal'
import ApartmentProfileModal from './ApartmentProfileModal'
import ConfirmDialog from '../shared/ConfirmDialog'

export interface ConfirmState {
  open: boolean
  title: string
  description: string
  onConfirm: () => void
}

type Level = 'yards' | 'buildings' | 'apartments' | 'all-buildings' | 'all-apartments'

interface AddressModalsProps {
  level: Level
  yards: YardBrief[]
  apartments: ApartmentBrief[]
  selectedYard: YardBrief | null
  selectedBuilding: BuildingBrief | null
  editingYard: YardBrief | null
  setEditingYard: Dispatch<SetStateAction<YardBrief | null>>
  editingBuilding: BuildingBrief | null
  setEditingBuilding: Dispatch<SetStateAction<BuildingBrief | null>>
  editingApartment: ApartmentBrief | null
  setEditingApartment: Dispatch<SetStateAction<ApartmentBrief | null>>
  addObjectOpen: boolean
  setAddObjectOpen: Dispatch<SetStateAction<boolean>>
  showCreateModal: boolean
  setShowCreateModal: Dispatch<SetStateAction<boolean>>
  showBulkCreate: boolean
  setShowBulkCreate: Dispatch<SetStateAction<boolean>>
  profileApartmentId: number | null
  setProfileApartmentId: Dispatch<SetStateAction<number | null>>
  confirmState: ConfirmState
  setConfirmState: Dispatch<SetStateAction<ConfirmState>>
}

// FE-09: все модалки справочника адресов (вынесено из AddressesPage без
// изменения поведения; условия рендера сохранены 1-в-1).
export default function AddressModals({
  level,
  yards,
  apartments,
  selectedYard,
  selectedBuilding,
  editingYard,
  setEditingYard,
  editingBuilding,
  setEditingBuilding,
  editingApartment,
  setEditingApartment,
  addObjectOpen,
  setAddObjectOpen,
  showCreateModal,
  setShowCreateModal,
  showBulkCreate,
  setShowBulkCreate,
  profileApartmentId,
  setProfileApartmentId,
  confirmState,
  setConfirmState,
}: AddressModalsProps) {
  const { t } = useTranslation()

  return (
    <>
      {/* Yard edit modal */}
      {editingYard && (
        <YardFormModal yard={editingYard} onClose={() => setEditingYard(null)} />
      )}

      {/* Building edit modal */}
      {editingBuilding && (
        <BuildingFormModal
          building={editingBuilding}
          yardId={editingBuilding.yard_id}
          yards={yards}
          onClose={() => setEditingBuilding(null)}
        />
      )}

      {/* Unified create object modal */}
      <AddObjectModal
        open={addObjectOpen}
        onClose={() => setAddObjectOpen(false)}
        yards={yards}
        preselectedYardId={level === 'buildings' ? selectedYard?.id : undefined}
      />

      {/* Apartment modals */}
      {editingApartment && (
        <ApartmentFormModal
          apartment={editingApartment}
          buildingId={editingApartment.building_id}
          onClose={() => setEditingApartment(null)}
        />
      )}
      {showCreateModal && level === 'apartments' && selectedBuilding && (
        <ApartmentFormModal
          buildingId={selectedBuilding.id}
          onClose={() => setShowCreateModal(false)}
        />
      )}

      {showBulkCreate && selectedBuilding && (
        <BulkCreateModal
          buildingId={selectedBuilding.id}
          buildingAddress={selectedBuilding.address}
          onClose={() => setShowBulkCreate(false)}
        />
      )}

      {profileApartmentId !== null && (
        <ApartmentProfileModal
          apartmentId={profileApartmentId}
          onClose={() => setProfileApartmentId(null)}
          onEdit={() => {
            const apt = apartments?.find(a => a.id === profileApartmentId)
            if (apt) {
              setProfileApartmentId(null)
              setEditingApartment(apt)
            }
          }}
        />
      )}

      <ConfirmDialog
        open={confirmState.open}
        onOpenChange={(open) => setConfirmState(prev => ({ ...prev, open }))}
        title={confirmState.title}
        description={confirmState.description}
        confirmLabel={t('common.delete')}
        onConfirm={confirmState.onConfirm}
        variant="danger"
      />
    </>
  )
}
