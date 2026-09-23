import { useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import type {
  Meter,
  MeterCreatePayload,
  ObjectNode,
  Provider,
  ResourceType,
  Unit,
} from '../api/types';

interface ConsumerDraft {
  object_id: string;
  description: string;
}

interface MeterFormProps {
  mode: 'create' | 'edit';
  initial?: Meter;
  pending?: boolean;
  error?: string | null;
  submitLabel?: string;
  onSubmit: (payload: MeterCreatePayload) => void;
  onCancel: () => void;
}

export function MeterForm({
  mode,
  initial,
  pending,
  error,
  submitLabel,
  onSubmit,
  onCancel,
}: MeterFormProps) {
  const { t } = useTranslation();
  const [meterNumber, setMeterNumber] = useState(initial?.meter_number ?? '');
  const [name, setName] = useState(initial?.name ?? '');
  const [resourceType, setResourceType] = useState<ResourceType>(
    initial?.resource_type ?? 'electricity',
  );
  const [unit, setUnit] = useState<Unit>(initial?.unit ?? 'kWh');
  const [description, setDescription] = useState(initial?.description ?? '');
  const [installLocation, setInstallLocation] = useState(initial?.install_location ?? '');
  const [primaryObjectId, setPrimaryObjectId] = useState(initial?.primary_object_id ?? '');
  const [providerId, setProviderId] = useState(initial?.provider_id ?? '');
  const [providerAccount, setProviderAccount] = useState(initial?.provider_account ?? '');
  const [serialNumber, setSerialNumber] = useState(initial?.serial_number ?? '');
  const [coefficient, setCoefficient] = useState(initial?.coefficient ?? '1');
  const [maxDigits, setMaxDigits] = useState(initial?.max_digits?.toString() ?? '');
  const [note, setNote] = useState(initial?.note ?? '');
  const [consumers, setConsumers] = useState<ConsumerDraft[]>(
    (initial?.consumers ?? []).map((c) => ({
      object_id: c.object_id,
      description: c.description ?? '',
    })),
  );

  const objectsQuery = useQuery({
    queryKey: ['objects', 'all'],
    queryFn: () => api<ObjectNode[]>('/v1/objects', { params: { status: 'active' } }),
  });
  const providersQuery = useQuery({
    queryKey: ['providers'],
    queryFn: () => api<Provider[]>('/v1/providers'),
  });

  const objects = objectsQuery.data ?? [];
  const providers = providersQuery.data ?? [];

  const changeResourceType = (rt: ResourceType) => {
    setResourceType(rt);
    setUnit(rt === 'electricity' ? 'kWh' : 'm3');
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit({
      meter_number: meterNumber.trim(),
      name: name.trim(),
      resource_type: resourceType,
      unit,
      description: description.trim(),
      install_location: installLocation.trim(),
      primary_object_id: primaryObjectId,
      provider_id: providerId || null,
      provider_account: providerAccount.trim() || null,
      serial_number: serialNumber.trim() || null,
      coefficient: coefficient || '1',
      max_digits: maxDigits ? Number(maxDigits) : null,
      note: note.trim() || null,
      consumers: consumers
        .filter((c) => c.object_id)
        .map((c) => ({ object_id: c.object_id, description: c.description.trim() || null })),
    });
  };

  const requiredFilled =
    (mode === 'edit' || meterNumber.trim()) &&
    name.trim() &&
    description.trim() &&
    installLocation.trim() &&
    primaryObjectId;

  return (
    <form className="meter-form" onSubmit={submit}>
      {mode === 'create' && (
        <div className="form-row">
          <label className="field">
            <span>{t('resourceAccounting.meterForm.meterNumber')}</span>
            <input value={meterNumber} onChange={(e) => setMeterNumber(e.target.value)} />
          </label>
          <label className="field">
            <span>{t('resourceAccounting.meterForm.resource')}</span>
            <select
              value={resourceType}
              onChange={(e) => changeResourceType(e.target.value as ResourceType)}
            >
              <option value="electricity">{t('resourceAccounting.meterForm.electricityOption')}</option>
              <option value="cold_water">{t('resourceAccounting.meterForm.coldWaterOption')}</option>
            </select>
          </label>
        </div>
      )}
      <label className="field">
        <span>{t('resourceAccounting.meterForm.name')}</span>
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="field">
        <span>{t('resourceAccounting.meterForm.description')}</span>
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
      </label>
      <div className="form-row">
        <label className="field">
          <span>{t('resourceAccounting.meterForm.installLocation')}</span>
          <input value={installLocation} onChange={(e) => setInstallLocation(e.target.value)} />
        </label>
        <label className="field">
          <span>{t('resourceAccounting.meterForm.primaryObject')}</span>
          <select value={primaryObjectId} onChange={(e) => setPrimaryObjectId(e.target.value)}>
            <option value="">{t('resourceAccounting.meterForm.choose')}</option>
            {objects.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="form-row">
        <label className="field">
          <span>{t('resourceAccounting.meterForm.provider')}</span>
          <select value={providerId ?? ''} onChange={(e) => setProviderId(e.target.value)}>
            <option value="">—</option>
            {providers
              .filter((p) => p.is_active)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
          </select>
        </label>
        <label className="field">
          <span>{t('resourceAccounting.meterForm.providerAccount')}</span>
          <input value={providerAccount ?? ''} onChange={(e) => setProviderAccount(e.target.value)} />
        </label>
      </div>
      <div className="form-row">
        <label className="field">
          <span>{t('resourceAccounting.meterForm.serialNumber')}</span>
          <input value={serialNumber ?? ''} onChange={(e) => setSerialNumber(e.target.value)} />
        </label>
        <label className="field">
          <span>{t('resourceAccounting.meterForm.coefficient')}</span>
          <input
            inputMode="decimal"
            value={coefficient}
            onChange={(e) => setCoefficient(e.target.value)}
          />
        </label>
        <label className="field">
          <span>{t('resourceAccounting.meterForm.maxDigits')}</span>
          <input
            inputMode="numeric"
            value={maxDigits}
            onChange={(e) => setMaxDigits(e.target.value.replace(/\D/g, ''))}
          />
        </label>
      </div>
      <label className="field">
        <span>{t('resourceAccounting.meterForm.note')}</span>
        <input value={note ?? ''} onChange={(e) => setNote(e.target.value)} />
      </label>

      <fieldset className="consumers-fieldset">
        <legend>{t('resourceAccounting.meterForm.consumers')}</legend>
        {consumers.map((c, idx) => (
          <div className="form-row consumer-row" key={idx}>
            <select
              value={c.object_id}
              onChange={(e) =>
                setConsumers((prev) =>
                  prev.map((item, i) => (i === idx ? { ...item, object_id: e.target.value } : item)),
                )
              }
            >
              <option value="">{t('resourceAccounting.meterForm.chooseObject')}</option>
              {objects.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
            <input
              placeholder={t('resourceAccounting.meterForm.consumerDescription')}
              value={c.description}
              onChange={(e) =>
                setConsumers((prev) =>
                  prev.map((item, i) =>
                    i === idx ? { ...item, description: e.target.value } : item,
                  ),
                )
              }
            />
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={() => setConsumers((prev) => prev.filter((_, i) => i !== idx))}
              aria-label={t('resourceAccounting.meterForm.removeConsumer')}
            >
              ×
            </button>
          </div>
        ))}
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => setConsumers((prev) => [...prev, { object_id: '', description: '' }])}
        >
          {t('resourceAccounting.meterForm.addConsumer')}
        </button>
      </fieldset>

      {error && <div className="form-error">{error}</div>}
      <div className="modal-actions">
        <button type="button" className="btn" onClick={onCancel}>
          {t('resourceAccounting.common.cancel')}
        </button>
        <button type="submit" className="btn btn-primary" disabled={!requiredFilled || pending}>
          {pending ? t('resourceAccounting.common.saving') : (submitLabel ?? t('resourceAccounting.common.save'))}
        </button>
      </div>
    </form>
  );
}
