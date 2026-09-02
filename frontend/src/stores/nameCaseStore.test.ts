import { describe, it, expect, beforeEach } from 'vitest'

import { NAME_CASE_STORAGE_KEY, readStoredNameCase, useNameCaseStore } from './nameCaseStore'

// Предпочтение «ФИО заглавными» живёт в localStorage устройства (как тема),
// без бэка. Стор — zustand-синглтон: любой потребитель ре-рендерится при
// переключении из сайдбара.

beforeEach(() => {
  localStorage.clear()
  useNameCaseStore.setState({ mode: 'title' })
})

describe('nameCaseStore', () => {
  it('дефолт — title, ключ storage стабилен', () => {
    expect(useNameCaseStore.getState().mode).toBe('title')
    expect(NAME_CASE_STORAGE_KEY).toBe('uk.nameCase')
  })

  it('читает сохранённый caps из localStorage', () => {
    localStorage.setItem(NAME_CASE_STORAGE_KEY, 'caps')
    expect(readStoredNameCase()).toBe('caps')
  })

  it('мусор в storage → title', () => {
    localStorage.setItem(NAME_CASE_STORAGE_KEY, 'upper')
    expect(readStoredNameCase()).toBe('title')
  })

  it('setMode пишет в storage', () => {
    useNameCaseStore.getState().setMode('caps')
    expect(useNameCaseStore.getState().mode).toBe('caps')
    expect(localStorage.getItem(NAME_CASE_STORAGE_KEY)).toBe('caps')
  })

  it('toggle переключает туда и обратно', () => {
    useNameCaseStore.getState().toggle()
    expect(useNameCaseStore.getState().mode).toBe('caps')
    expect(localStorage.getItem(NAME_CASE_STORAGE_KEY)).toBe('caps')
    useNameCaseStore.getState().toggle()
    expect(useNameCaseStore.getState().mode).toBe('title')
    expect(localStorage.getItem(NAME_CASE_STORAGE_KEY)).toBe('title')
  })
})
