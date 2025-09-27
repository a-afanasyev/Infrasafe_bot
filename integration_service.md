# Integration Service Architecture

## 1. Mission & Scope
- **Purpose**: Single integration hub between core microservices (requests, users, notifications, media) and external systems (Google Sheets, Excel/CSV, document storage, future web/mobile apps).
- **Primary Goals**:
  - Decouple external integrations from business microservices.
  - Provide consistent, versioned APIs and event streams for third-party consumers.
  - Offer pluggable connectors for current and future channels (Google Workspace, MS Office, REST partners).
  - Ensure observability, retries, and resilience of outbound communications.

## 2. Current Migration Context
- Transitioning monolithic features into microservices; Request Service and related domains already split out.
- Need to maintain existing Google Sheets sync and document exports while enabling future channels.
- Prefer clean deployment (no legacy data) but connectors must support initial backfill jobs from new services if required.
- Integration Service should be ready to consume events from Request Service once it goes live.

## 3. Core Responsibilities
1. **Inbound Synchronisation**: Receive domain events (Kafka/Redis Streams) from microservices and transform them for external systems.
2. **Outbound APIs**: Expose REST/GraphQL endpoints for web/mobile apps or partners needing aggregated data.
3. **Batch Jobs**: Scheduled exports/imports (daily sheet sync, periodic document generation, archival reports).
4. **Connector Management**: Encapsulate credentials, rate limiting, and vendor-specific logic.
5. **Transformation Layer**: Map internal schemas to external data formats (CSV, XLSX, Sheets, DOCX templates).
6. **Monitoring & Alerting**: Track delivery success, failures, latency, and provide dashboards/alerts.

## 4. High-Level Architecture
```
                  +-----------------+            +------------------+
   Core Events -->| Event Consumer  |----+-----> | Transformation   |
 (Kafka/Streams)  |  (Redis/Kafka)  |    |       |   Pipelines      |
                  +-----------------+    |       +------------------+
                                          |                   |
                                          |                   v
                                  +----------------+    +----------------+
                                  | Connector Bus  |--> | External APIs  |
                                  |  (Plugins)     |    | (Sheets, Drive,|
                                  +----------------+    |  Excel, etc.) |
                                          ^                   |
                                          |                   v
             +----------------+    +-----------------+    +----------------+
 Frontend -> | Integration    |<-- | API Gateway      |<--| Web/Mobile App |
  Clients    |   Service API  |    | (REST/GraphQL)  |    +----------------+
             +----------------+    +-----------------+
```

### Subsystems
- **Event Ingestion**: Subscribes to domain events via Kafka/Redis Streams (e.g., `request.status.changed`, `request.created`).
- **Transformation Pipelines**: Normalise payloads, enrich with additional data via microservice REST calls, prepare external format.
- **Connector Bus**: Dynamically loads connector modules (GoogleSheetsConnector, ExcelConnector, DocumentConnector).
- **Outbound API Layer**: Serves aggregated data for web/mobile clients (future GraphQL) and third-party consumers.
- **Scheduler/Job Runner**: Cron or workflow engine (e.g., Temporal, Celery beat) for periodic sync/export tasks.
- **Observability Layer**: Central logging, metrics, tracing, dead-letter queues.

## 5. Service Modules
| Module | Responsibility |
|--------|----------------|
| `app/api` | REST/GraphQL endpoints for internal/external clients. Versioned (v1, v2) to allow contract stability. |
| `app/connectors` | Vendor-specific adapters (Google Sheets, OneDrive/SharePoint, CSV/XLSX, PDFs). Implement common interface `BaseConnector`. |
| `app/events` | Consumers/producers. Handles subscription to Redis Streams or Kafka topics, ensures idempotency and dead-letter handling. |
| `app/services` | Business logic: transformation services, orchestration of connector workflows, caching. |
| `app/jobs` | Scheduled tasks (cron definitions) for periodic exports, audits, cleanups. |
| `app/storage` | Optional persistent storage (PostgreSQL) to keep sync metadata, tokens, audit logs, connector status. |
| `app/security` | Token validation, service-to-service authentication, secrets management integration (Vault). |

## 6. Data Flows
1. **Event-driven Sync**
   - Request Service publishes event to Kafka/Redis.
   - Integration Service consumes, fetches enriched data via Request/User services.
   - Transformer prepares row for Google Sheets, pushes via connector.
   - Connector stores operation result and emits success/failure metrics.

2. **Scheduled Export**
   - Job runner triggers export (e.g., daily XLSX report).
   - Fetch aggregated data from services or local cache.
   - Generate file using `ExcelConnector`, upload to document store or email distribution list.

3. **Web/Mobile API**
   - Frontend hits `/api/v1/integration/requests/overview`.
   - Integration Service aggregates data from cache or Request Service APIs, returns JSON/GraphQL payload.
   - Supports pagination, filtering parity with Request Service.

4. **Bulk Import (Future)**
   - Upload Excel/CSV through Integration API.
   - Validate schema, convert to internal format, call Request Service bulk endpoint.
   - Track import progress via job status endpoints.

## 7. External Connectors
### Google Sheets Connector
- Handles OAuth2, token refresh, sheet schema management.
- Maintains mapping of internal fields to sheet columns (configurable).
- Supports append, update, batch clear/rewrite.

### Excel/CSV Connector
- Uses library (e.g., openpyxl, pandas) for XLSX creation/parsing.
- Validates templates, handles localization (date/time formats).
- Provides storage integration (S3, Google Drive, local export directory).

### Document Connector
- Generates DOCX/PDF via templating (Jinja2 + docxtpl, PDFkit).
- Supports signatures, stamping, storing in document management systems.

### Web/Mobile API Layer
- Exposes normalized endpoints for UI clients.
- Potential GraphQL gateway for aggregated data (requests + comments + analytics).
- Integrates with Auth Service for JWT validation.

## 8. Technical Stack
- **Runtime**: FastAPI (REST), Strawberry/Graphene (GraphQL optional), asyncio for concurrency.
- **Message Broker**: Redis Streams (initial) with migration path to Kafka when volume grows.
- **Persistence**: PostgreSQL for metadata, Redis for caching, Vault for secrets.
- **Task Orchestration**: Celery + Redis/AMQP or Temporal.io for complex workflows.
- **Deploy**: Docker container, orchestrated via Kubernetes/Compose similar to other microservices.
- **Observability**: OpenTelemetry traces, Prometheus metrics (`integration_connector_status`, `external_call_latency`), Grafana dashboards.

## 9. API Surface (Draft)
### REST
- `GET /api/v1/integration/requests/summary` – aggregated stats for dashboards.
- `GET /api/v1/integration/exports/{job_id}` – status of scheduled exports.
- `POST /api/v1/integration/imports` – upload XLS/CSV for bulk import.
- `GET /api/v1/integration/connectors` – list connectors, health/status.
- `POST /api/v1/integration/connectors/{name}/trigger` – manual sync trigger.

### Webhooks (Optional)
- `POST /webhooks/google/sheets` – inbound triggers from Google App Scripts.
- `POST /webhooks/documents/callback` – status updates from doc processing.

### Authentication
- Internal services use service-to-service JWT validated via Auth Service (`X-Service-Token`).
- External apps use OAuth2 (integration service as resource server) or API keys.

## 10. Deployment & Scaling
- **Pods**: `integration-service-api`, `integration-service-workers` (jobs), `integration-service-connectors` (optional separate autoscaling group).
- **Horizontal Scaling**: Stateless API pods; connectors maintain token caches in Redis/PostgreSQL.
- **Resilience**: Circuit breakers for external APIs, exponential backoff retries, fallback queues.
- **Feature Flags**: Toggle connectors per environment via config service.

## 11. Security & Compliance
- Store external credentials in Vault/KMS; rotate via scheduled jobs.
- Enforce least privilege scopes on Google API (read/write per sheet).
- Audit log every external operation (who/when/what) in PostgreSQL.
- Rate limiting per connector to avoid vendor throttling.
- Data classification: ensure exports respect PII policies; optionally add anonymisation for analytics endpoints.

## 12. Migration Plan
1. **Phase 0 (Design)**
   - Finalize contracts with existing services (Request, User, Notification).
   - Implement feature flags to keep existing Google Sheets sync running during handover.
2. **Phase 1 (Foundation)**
   - Scaffold Integration Service project.
   - Implement base infrastructure: service-to-service auth, PostgreSQL metadata store, event consumers.
   - Deploy read-only Google Sheets connector (mirroring current functionality).
3. **Phase 2 (Parity)**
   - Migrate existing Google Sheets sync from monolith/Request Service to Integration Service.
   - Add export job scheduling, metrics, alerting.
   - Switch Telegram bot to rely on Integration Service for exports (if applicable).
4. **Phase 3 (Expansion)**
   - Introduce Excel/CSV imports/exports.
   - Implement Document connector (PDF/DOCX generation).
   - Provide REST endpoints for web/mobile prototypes (summary dashboards, export status).
5. **Phase 4 (Optimisation)**
   - Enable event-driven updates (push vs batch).
   - Add GraphQL gateway for richer clients.
   - Evaluate migration from Redis Streams to Kafka if throughput demands increase.

## 13. Risks & Mitigations
| Risk | Impact | Mitigation |
|------|--------|-----------|
| Connector failures causing data drift | High | Implement retries, DLQ, dashboards, alerting. |
| Credential management complexity | Medium | Centralize in Vault, automated rotation scripts. |
| Schema drift between services | Medium | Maintain shared schema definitions (protobuf/JSONSchema), versioned contracts. |
| Vendor API limits | Medium | Rate limiting, batching, incremental sync. |
| Growing scope (web/mobile feature creep) | Medium | Document MVP and backlog, enforce API versioning. |

## 14. Backlog & Next Steps
- [ ] Create repository structure and CI pipeline (lint, tests, docker build).
- [ ] Define event contracts (`request.created`, `request.updated`, `comment.added`).
- [ ] Build Google Sheets connector prototype with parity dataset.
- [ ] Establish service-to-service auth tokens and register with Auth Service.
- [ ] Write integration tests using mock external APIs.
- [ ] Prepare monitoring dashboards (Grafana, Prometheus alerts).
- [ ] Document onboarding guide for new connectors and external partners.

---
**Outcome**: Integration Service becomes the single gateway for all external systems, enabling the new microservice architecture to evolve independently while supporting future web/mobile clients.
