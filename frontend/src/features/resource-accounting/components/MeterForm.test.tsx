import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { I18nextProvider } from 'react-i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { server } from '../../../test/msw/server';
import { testI18n } from '../../../test/test-utils';
import { configureResourceApi } from '../api/client';
import type { Meter } from '../api/types';
import { MeterForm } from './MeterForm';

// TEST-068 (порция resource-accounting): форма счётчика — обязательные поля,
// смена ресурса меняет единицу, нормализация payload, потребители.

const BASE = 'http://localhost/res';
const OBJECTS = [{ id: 'o1', name: 'Корпус А', code: null, type_id: null, parent_id: null, description: null, sort_order: 0, is_active: true, tags: [] }];
const PROVIDERS = [
  { id: 'p1', name: 'Энергосбыт', contact: null, is_active: true },
  { id: 'p2', name: 'Закрытый', contact: null, is_active: false },
];

function renderForm(props: Partial<Parameters<typeof MeterForm>[0]> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onSubmit = vi.fn(); const onCancel = vi.fn();
  render(
    <I18nextProvider i18n={testI18n}>
      <QueryClientProvider client={queryClient}>
        <MeterForm mode="create" onSubmit={onSubmit} onCancel={onCancel} {...props} />
      </QueryClientProvider>
    </I18nextProvider>,
  );
  return { onSubmit, onCancel };
}

beforeEach(() => {
  configureResourceApi({ baseUrl: BASE, onUnauthorized: () => {} });
  server.use(
    http.get(`${BASE}/v1/objects`, () => HttpResponse.json({ data: OBJECTS })),
    http.get(`${BASE}/v1/providers`, () => HttpResponse.json({ data: PROVIDERS })),
  );
});

describe('MeterForm — создание', () => {
  it('кнопка заблокирована до заполнения обязательных; вода меняет единицу; payload нормализован', async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm();
    const submit = screen.getByRole('button', { name: 'Сохранить' });
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText('Номер счётчика *'), ' M-1 ');
    await user.selectOptions(screen.getByLabelText('Ресурс *'), 'cold_water');
    await user.type(screen.getByLabelText('Название *'), 'ХВС подвал');
    await user.type(screen.getByLabelText('Описание *'), 'Общедомовой');
    await user.type(screen.getByLabelText('Место установки *'), 'Подвал');
    expect(submit).toBeDisabled(); // основной объект ещё не выбран
    await screen.findByRole('option', { name: 'Корпус А' });
    await user.selectOptions(screen.getByLabelText('Основной объект *'), 'o1');
    expect(submit).toBeEnabled();

    expect(screen.queryByRole('option', { name: 'Закрытый' })).not.toBeInTheDocument(); // неактивный поставщик скрыт
    await user.selectOptions(screen.getByLabelText('Поставщик'), 'p1');
    await user.type(screen.getByLabelText('Разрядность'), '6x'); // нецифры отбрасываются
    await user.click(screen.getByRole('button', { name: '+ Добавить потребителя' }));
    await user.click(screen.getByRole('button', { name: '+ Добавить потребителя' }));
    const consumerSelects = screen.getAllByRole('combobox').slice(-2);
    await user.selectOptions(consumerSelects[0], 'o1');
    await user.type(screen.getAllByPlaceholderText('Описание')[0], ' Лифт ');
    await user.click(screen.getAllByRole('button', { name: 'Удалить потребителя' })[1]);
    await user.click(submit);

    expect(onSubmit).toHaveBeenCalledWith({
      meter_number: 'M-1', name: 'ХВС подвал', resource_type: 'cold_water', unit: 'm3',
      description: 'Общедомовой', install_location: 'Подвал', primary_object_id: 'o1',
      provider_id: 'p1', provider_account: null, serial_number: null, coefficient: '1',
      max_digits: 6, note: null, consumers: [{ object_id: 'o1', description: 'Лифт' }],
    });
  });

  it('pending/ошибка: кнопка «Сохранение…» заблокирована, текст ошибки виден; «Отмена» зовёт onCancel', async () => {
    const user = userEvent.setup();
    const { onCancel } = renderForm({ pending: true, error: 'Номер уже занят' });
    expect(screen.getByRole('button', { name: 'Сохранение…' })).toBeDisabled();
    expect(screen.getByText('Номер уже занят')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Отмена' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});

describe('MeterForm — правка', () => {
  it('без номера/ресурса, поля из initial, потребители из initial, свой submitLabel', async () => {
    const user = userEvent.setup();
    const initial = {
      id: 'm1', meter_number: 'M-1', name: 'ХВС', resource_type: 'cold_water', unit: 'm3', description: 'Опис',
      install_location: 'Подвал', primary_object_id: 'o1', provider_id: 'p1', provider_account: '123',
      serial_number: 'SN', coefficient: '2', max_digits: 5, note: 'Заметка', is_active: true,
      consumers: [{ object_id: 'o1', description: null }],
    } as unknown as Meter;
    const { onSubmit } = renderForm({ mode: 'edit', initial, submitLabel: 'Обновить' });

    expect(screen.queryByLabelText('Номер счётчика *')).not.toBeInTheDocument();
    expect((screen.getByLabelText('Название *') as HTMLInputElement).value).toBe('ХВС');
    expect((screen.getByLabelText('Лицевой счёт') as HTMLInputElement).value).toBe('123');
    await screen.findAllByRole('option', { name: 'Корпус А' }); // основной объект + потребитель
    const submit = screen.getByRole('button', { name: 'Обновить' });
    expect(submit).toBeEnabled();
    await user.click(submit);

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      meter_number: 'M-1', unit: 'm3', provider_account: '123', serial_number: 'SN', coefficient: '2',
      max_digits: 5, note: 'Заметка', consumers: [{ object_id: 'o1', description: null }],
    }));
  });
});
