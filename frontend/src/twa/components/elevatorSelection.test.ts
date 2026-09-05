import { describe, it, expect } from 'vitest'
import { EMPTY_ELEVATOR_SELECTION, isElevatorSelectionComplete, resolveBuildingId } from './elevatorSelection'

const APARTMENTS = [{ id: 5, building_id: 12 }, { id: 6 }]

describe('resolveBuildingId', () => {
  it('без адреса — null', () => {
    expect(resolveBuildingId('apartment', null, APARTMENTS)).toBeNull()
  })

  it('дом — сам id', () => {
    expect(resolveBuildingId('building', 12, APARTMENTS)).toBe(12)
  })

  it('квартира — building_id из справочника адресов; неизвестная/без дома — null', () => {
    expect(resolveBuildingId('apartment', 5, APARTMENTS)).toBe(12)
    expect(resolveBuildingId('apartment', 6, APARTMENTS)).toBeNull()
    expect(resolveBuildingId('apartment', 99, APARTMENTS)).toBeNull()
  })

  it('двор — null (лифт требует дом)', () => {
    expect(resolveBuildingId('yard', 1, APARTMENTS)).toBeNull()
  })
})

describe('isElevatorSelectionComplete', () => {
  it('нужны и лифт, и ответ «работает?»', () => {
    expect(isElevatorSelectionComplete(EMPTY_ELEVATOR_SELECTION)).toBe(false)
    expect(isElevatorSelectionComplete({ ...EMPTY_ELEVATOR_SELECTION, elevatorId: 7 })).toBe(false)
    expect(isElevatorSelectionComplete({ ...EMPTY_ELEVATOR_SELECTION, operational: true })).toBe(false)
    expect(isElevatorSelectionComplete({ ...EMPTY_ELEVATOR_SELECTION, elevatorId: 7, operational: false })).toBe(true)
  })
})
