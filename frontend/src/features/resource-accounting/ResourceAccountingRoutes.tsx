import { Navigate, Route, Routes } from 'react-router-dom';
import { useResourceAuth } from './auth/ResourceAuthContext';
import { isAdmin, isMeterEntry } from './auth/roles';
import { DashboardPage } from './pages/DashboardPage';
import { WorksheetPage } from './pages/WorksheetPage';
import { MetersPage } from './pages/MetersPage';
import { MeterDetailPage } from './pages/MeterDetailPage';
import { ObjectsPage } from './pages/ObjectsPage';
import { ExportsPage } from './pages/ExportsPage';
import { ProvidersPage } from './pages/ProvidersPage';
import { AuditPage } from './pages/AuditPage';

/**
 * Роуты раздела (относительные пути) — монтируются хостом под своим `<Route path="…/*">`.
 * Роль-осведомлён: контролёр (resource_meter_entry) получает единственную страницу ввода;
 * журнал доступен только админу. Ссылки строятся через basePath (см. ResourceAccountingProvider).
 */
export function ResourceAccountingRoutes() {
  const { role, loading } = useResourceAuth();

  if (loading) return null; // ждём идентичность (self-bootstrap /v1/auth/me)

  if (isMeterEntry(role)) {
    return (
      <Routes>
        <Route path="*" element={<WorksheetPage entryMode />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route index element={<DashboardPage />} />
      <Route path="worksheet" element={<WorksheetPage />} />
      <Route path="meters" element={<MetersPage />} />
      <Route path="meters/:id" element={<MeterDetailPage />} />
      <Route path="objects" element={<ObjectsPage />} />
      <Route path="exports" element={<ExportsPage />} />
      <Route path="providers" element={<ProvidersPage />} />
      {isAdmin(role) && <Route path="audit" element={<AuditPage />} />}
      <Route path="*" element={<Navigate to="." replace />} />
    </Routes>
  );
}
