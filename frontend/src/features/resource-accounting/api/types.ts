export type Role =
  | 'resource_admin'
  | 'resource_operator'
  | 'resource_reviewer'
  | 'resource_viewer'
  | 'resource_meter_entry';

export interface AuthUser {
  user_id: string;
  display_name: string;
  role: Role;
}

export type ResourceType = 'electricity' | 'cold_water';
export type Unit = 'kWh' | 'm3';

export const RESOURCE_TYPE_LABELS: Record<ResourceType, string> = {
  electricity: 'Электроэнергия',
  cold_water: 'Холодная вода',
};

export interface ObjectType {
  id: string;
  name: string;
  is_active: boolean;
}

export interface Tag {
  id: string;
  name: string;
  is_active: boolean;
}

export interface Provider {
  id: string;
  name: string;
  contact: string | null;
  export_template?: string | null;
  is_active: boolean;
}

export interface ObjectNode {
  id: string;
  name: string;
  code: string | null;
  type_id: string | null;
  parent_id: string | null;
  description: string | null;
  sort_order: number;
  is_active: boolean;
  tags: Tag[];
}

export interface ConsumerLink {
  id?: string;
  object_id: string;
  object_name?: string | null;
  link_type?: string;
  description: string | null;
  allocation_percent?: string | null;
}

export type MeterStatus = 'active' | 'decommissioned' | 'archived';

export const METER_STATUS_LABELS: Record<string, string> = {
  active: 'Активен',
  decommissioned: 'Снят',
  archived: 'Архив',
};

export interface Meter {
  id: string;
  meter_number: string;
  name: string;
  resource_type: ResourceType;
  unit: Unit;
  description: string;
  install_location: string;
  status: MeterStatus;
  primary_object_id: string;
  primary_object_name: string | null;
  provider_id: string | null;
  provider_account: string | null;
  serial_number: string | null;
  coefficient: string;
  max_digits: number | null;
  installed_at: string | null;
  removed_at?: string | null;
  replaces_meter_id?: string | null;
  note: string | null;
  tags: Tag[];
  consumers: ConsumerLink[];
}

export interface MeterCreatePayload {
  meter_number: string;
  name: string;
  resource_type: ResourceType;
  unit: Unit;
  description: string;
  install_location: string;
  primary_object_id: string;
  provider_id?: string | null;
  provider_account?: string | null;
  serial_number?: string | null;
  coefficient?: string;
  max_digits?: number | null;
  installed_at?: string | null;
  note?: string | null;
  consumers?: { object_id: string; description?: string | null }[];
}

export interface ListMeta {
  total: number;
  page: number;
  per_page: number;
}

export type PeriodStatus = 'open' | 'review' | 'submitted' | 'closed';

export interface Period {
  id: string;
  month: string;
  status: PeriodStatus;
}

export type ReadingStatus = 'ok' | 'warning' | 'error' | 'missing';
export type ReadingKind = 'normal' | 'rollover' | 'replacement' | 'correction';
export type MissingReason = 'no_access' | 'broken' | 'replaced' | 'other';

export interface WorksheetReading {
  id: string;
  meter_id: string;
  value: string | null;
  read_at: string | null;
  kind: ReadingKind;
  previous_value: string | null;
  consumption: string | null;
  status: ReadingStatus;
  validation_message: string | null;
  missing_reason: MissingReason | null;
  comment: string | null;
}

export interface WorksheetRow {
  meter_id: string;
  meter_number: string;
  meter_name: string;
  resource_type: ResourceType;
  unit: Unit;
  description: string;
  primary_object_id: string;
  primary_object_name: string;
  consumers: string[];
  provider_name: string | null;
  coefficient: string;
  previous_value: string | null;
  previous_read_at: string | null;
  reading: WorksheetReading | null;
}

export interface Worksheet {
  period: Period;
  rows: WorksheetRow[];
}

export interface ValidationSummary {
  active_meters: number;
  entered: number;
  not_entered: number;
  by_status: Record<string, number>;
  warnings_without_comment: number;
  errors: number;
  can_submit: boolean;
}

export interface AnalyticsPoint {
  month: string;
  reading: string | null;
  consumption: string | null;
  status: ReadingStatus | null;
  kind?: string;
  missing: boolean;
}

export interface MeterAnalytics {
  meter_id: string;
  meter_number: string;
  unit: Unit;
  points: AnalyticsPoint[];
  stats: {
    avg_3m: number | null;
    avg_6m: number | null;
    avg_12m: number | null;
    change_abs: number | null;
    change_pct: number | null;
    year_over_year: {
      previous_year: number;
      current: number;
      change_pct: number | null;
    } | null;
  };
}

export type ExportFormat = 'xlsx' | 'csv' | 'pdf';

export interface ExportItem {
  id: string;
  period_month: string | null;
  provider_id: string | null;
  provider_name: string | null;
  format: ExportFormat;
  status: string;
  is_correction: boolean;
  filters: Record<string, unknown> | null;
  file_name: string | null;
  checksum: string | null;
  row_count: number | null;
  created_at: string;
  sent_at: string | null;
  sent_channel: string | null;
  sent_comment: string | null;
}

export interface AuditEntry {
  id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  before: unknown;
  after: unknown;
  actor_name: string | null;
  correlation_id: string | null;
  created_at: string;
}

export interface SparklinePoint {
  month: string;
  consumption: number;
}

export interface MetersSparklines {
  months: number;
  series: Record<string, SparklinePoint[]>;
}
