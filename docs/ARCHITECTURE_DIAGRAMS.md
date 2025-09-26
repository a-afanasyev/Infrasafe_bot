# 📊 АРХИТЕКТУРНЫЕ ДИАГРАММЫ
## UK Management Bot - Microservices Architecture Diagrams

---

## 1. HIGH-LEVEL ARCHITECTURE

```mermaid
graph TB
    subgraph "Client Layer"
        TG[Telegram Users]
        WEB[Web Interface]
        MOB[Mobile App]
    end

    subgraph "Gateway Layer"
        AG[API Gateway]
        BG[Bot Gateway]
    end

    subgraph "Service Layer"
        AUTH[Auth Service]
        USER[User Service]
        REQ[Request Service]
        SHIFT[Shift Service]
        NOTIFY[Notification Service]
        ANAL[Analytics Service]
        AI[AI Service]
        INTG[Integration Service]
    end

    subgraph "Data Layer"
        PG1[(Auth DB)]
        PG2[(Users DB)]
        PG3[(Requests DB)]
        PG4[(Shifts DB)]
        CH[(Analytics DB)]
        REDIS[(Redis Cache)]
        MINIO[(File Storage)]
    end

    subgraph "Infrastructure"
        MQ[Message Queue]
        CONSUL[Service Registry]
        VAULT[Secrets Store]
    end

    TG --> BG
    WEB --> AG
    MOB --> AG
    
    BG --> AG
    
    AG --> AUTH
    AG --> USER
    AG --> REQ
    AG --> SHIFT
    AG --> NOTIFY
    AG --> ANAL
    AG --> AI
    AG --> INTG
    
    AUTH --> PG1
    USER --> PG2
    REQ --> PG3
    SHIFT --> PG4
    ANAL --> CH
    
    AUTH --> REDIS
    USER --> REDIS
    REQ --> REDIS
    SHIFT --> REDIS
    
    USER --> MINIO
    REQ --> MINIO
    
    REQ --> MQ
    SHIFT --> MQ
    NOTIFY -.-> MQ
    ANAL -.-> MQ
    AI -.-> MQ
    
    AUTH --> VAULT
    USER --> VAULT
    
    AUTH --> CONSUL
    USER --> CONSUL
    REQ --> CONSUL
    SHIFT --> CONSUL
```

---

## 2. SERVICE INTERACTIONS

```mermaid
sequenceDiagram
    participant U as User
    participant BG as Bot Gateway
    participant AG as API Gateway
    participant AS as Auth Service
    participant RS as Request Service
    participant US as User Service
    participant AI as AI Service
    participant NS as Notification Service
    participant MQ as Message Queue

    U->>BG: Create Request
    BG->>AG: POST /requests
    AG->>AS: Validate Token
    AS-->>AG: Token Valid
    AG->>RS: Create Request
    RS->>US: Get User Info
    US-->>RS: User Details
    RS->>AI: Auto-assign Request
    AI-->>RS: Assignment Result
    RS->>MQ: Publish request.created
    RS-->>AG: Request Created
    AG-->>BG: Response
    BG-->>U: Success Message
    
    MQ->>NS: request.created Event
    NS->>U: Send Notification
```

---

## 3. DATABASE SCHEMA

```mermaid
erDiagram
    USERS ||--o{ USER_ROLES : has
    USERS ||--o{ USER_SPECIALIZATIONS : has
    USERS ||--o{ REQUESTS : creates
    USERS ||--o{ SHIFTS : assigned
    
    REQUESTS ||--o{ REQUEST_ASSIGNMENTS : has
    REQUESTS ||--o{ REQUEST_COMMENTS : has
    REQUESTS ||--o{ REQUEST_HISTORY : has
    
    SHIFTS ||--o{ SHIFT_ASSIGNMENTS : has
    SHIFT_TEMPLATES ||--o{ SHIFTS : generates
    
    USERS {
        bigint id PK
        string telegram_id
        string first_name
        string last_name
        string email
        string phone
        json addresses
        string status
        timestamp created_at
    }
    
    REQUESTS {
        string request_number PK
        bigint user_id FK
        string category
        string status
        string address
        text description
        json media_files
        bigint executor_id FK
        timestamp created_at
    }
    
    SHIFTS {
        bigint id PK
        bigint user_id FK
        timestamp start_time
        timestamp end_time
        string status
        json coverage_areas
        integer max_requests
        float efficiency_score
    }
```

---

## 4. EVENT FLOW

```mermaid
graph LR
    subgraph "Request Events"
        RC[request.created]
        RA[request.assigned]
        RS[request.status_changed]
        RCO[request.completed]
    end
    
    subgraph "Shift Events"
        SC[shift.created]
        SS[shift.started]
        SE[shift.ended]
        ST[shift.transferred]
    end
    
    subgraph "Consumers"
        NS[Notification Service]
        AS[Analytics Service]
        AIS[AI Service]
    end
    
    RC --> NS
    RC --> AS
    RC --> AIS
    
    RA --> NS
    RA --> AS
    
    RS --> NS
    RS --> AS
    
    RCO --> NS
    RCO --> AS
    RCO --> AIS
    
    SC --> NS
    SC --> AS
    
    SS --> NS
    SS --> AS
    
    SE --> NS
    SE --> AS
    SE --> AIS
    
    ST --> NS
    ST --> AS
```

---

## 5. DEPLOYMENT ARCHITECTURE

```mermaid
graph TB
    subgraph "Production Cluster"
        subgraph "Zone A"
            NG1[Nginx Ingress]
            subgraph "Node 1"
                POD1[Auth Service Pod]
                POD2[User Service Pod]
            end
            subgraph "Node 2"
                POD3[Request Service Pod]
                POD4[Shift Service Pod]
            end
        end
        
        subgraph "Zone B"
            NG2[Nginx Ingress]
            subgraph "Node 3"
                POD5[Auth Service Pod]
                POD6[User Service Pod]
            end
            subgraph "Node 4"
                POD7[Request Service Pod]
                POD8[Shift Service Pod]
            end
        end
        
        subgraph "Data Zone"
            PG_MASTER[(PostgreSQL Master)]
            PG_SLAVE[(PostgreSQL Slave)]
            REDIS_MASTER[(Redis Master)]
            REDIS_SLAVE[(Redis Slave)]
        end
    end
    
    LB[Load Balancer]
    
    LB --> NG1
    LB --> NG2
    
    POD1 --> PG_MASTER
    POD2 --> PG_MASTER
    POD3 --> PG_MASTER
    POD4 --> PG_MASTER
    
    POD5 --> PG_SLAVE
    POD6 --> PG_SLAVE
    POD7 --> PG_SLAVE
    POD8 --> PG_SLAVE
    
    POD1 --> REDIS_MASTER
    POD5 --> REDIS_SLAVE
```

---

## 6. SECURITY ARCHITECTURE

```mermaid
graph TB
    subgraph "External"
        USER[User]
        ATTACKER[Attacker]
    end
    
    subgraph "Edge Security"
        CDN[CloudFlare CDN]
        WAF[Web Application Firewall]
    end
    
    subgraph "Network Security"
        VPN[VPN Gateway]
        FW[Firewall]
        IDS[IDS/IPS]
    end
    
    subgraph "Application Security"
        AG[API Gateway]
        AUTH[Auth Service]
        VAULT[HashiCorp Vault]
    end
    
    subgraph "Internal Services"
        SVC[Microservices]
        DB[(Databases)]
    end
    
    USER --> CDN
    ATTACKER -.-> CDN
    CDN --> WAF
    WAF --> FW
    FW --> AG
    AG --> AUTH
    AUTH --> VAULT
    AUTH --> SVC
    SVC --> DB
    
    VPN --> IDS
    IDS --> SVC
    
    style ATTACKER fill:#f96,stroke:#333,stroke-width:2px
    style WAF fill:#9f6,stroke:#333,stroke-width:2px
    style FW fill:#9f6,stroke:#333,stroke-width:2px
    style IDS fill:#9f6,stroke:#333,stroke-width:2px
```

---

## 7. CI/CD PIPELINE

```mermaid
graph LR
    subgraph "Development"
        DEV[Developer]
        LOCAL[Local Test]
    end
    
    subgraph "Version Control"
        GIT[Git Repository]
        PR[Pull Request]
    end
    
    subgraph "CI Pipeline"
        BUILD[Build]
        TEST[Unit Tests]
        LINT[Code Quality]
        SEC[Security Scan]
        IMG[Build Image]
    end
    
    subgraph "CD Pipeline"
        STAGING[Deploy to Staging]
        E2E[E2E Tests]
        PERF[Performance Tests]
        PROD[Deploy to Production]
    end
    
    subgraph "Monitoring"
        MON[Monitoring]
        ALERT[Alerting]
    end
    
    DEV --> LOCAL
    LOCAL --> GIT
    GIT --> PR
    PR --> BUILD
    BUILD --> TEST
    TEST --> LINT
    LINT --> SEC
    SEC --> IMG
    IMG --> STAGING
    STAGING --> E2E
    E2E --> PERF
    PERF --> PROD
    PROD --> MON
    MON --> ALERT
    
    style BUILD fill:#ff9,stroke:#333,stroke-width:2px
    style TEST fill:#ff9,stroke:#333,stroke-width:2px
    style PROD fill:#9f9,stroke:#333,stroke-width:2px
```

---

## 8. DATA FLOW ARCHITECTURE

```mermaid
graph TB
    subgraph "Data Sources"
        APP[Applications]
        IOT[IoT Devices]
        EXT[External APIs]
    end
    
    subgraph "Ingestion Layer"
        KAFKA[Apache Kafka]
        API[REST APIs]
    end
    
    subgraph "Processing Layer"
        STREAM[Stream Processing]
        BATCH[Batch Processing]
        ML[ML Pipeline]
    end
    
    subgraph "Storage Layer"
        OLTP[(PostgreSQL)]
        OLAP[(ClickHouse)]
        LAKE[(Data Lake)]
        CACHE[(Redis)]
    end
    
    subgraph "Serving Layer"
        ANAL[Analytics Service]
        REPORT[Reporting Service]
        DASH[Dashboards]
    end
    
    APP --> API
    IOT --> KAFKA
    EXT --> KAFKA
    
    API --> STREAM
    KAFKA --> STREAM
    KAFKA --> BATCH
    
    STREAM --> OLTP
    STREAM --> CACHE
    BATCH --> OLAP
    BATCH --> LAKE
    
    LAKE --> ML
    ML --> OLAP
    
    OLTP --> ANAL
    OLAP --> ANAL
    CACHE --> ANAL
    
    ANAL --> REPORT
    ANAL --> DASH
```

---

## 9. MONITORING ARCHITECTURE

```mermaid
graph TB
    subgraph "Applications"
        SVC1[Service 1]
        SVC2[Service 2]
        SVC3[Service N]
    end
    
    subgraph "Collectors"
        PROM[Prometheus]
        LOKI[Loki]
        TEMPO[Tempo]
    end
    
    subgraph "Storage"
        METRICS[(Metrics Store)]
        LOGS[(Logs Store)]
        TRACES[(Traces Store)]
    end
    
    subgraph "Visualization"
        GRAF[Grafana]
        ALERT[Alert Manager]
    end
    
    subgraph "Notifications"
        SLACK[Slack]
        EMAIL[Email]
        PAGER[PagerDuty]
    end
    
    SVC1 --> PROM
    SVC2 --> PROM
    SVC3 --> PROM
    
    SVC1 --> LOKI
    SVC2 --> LOKI
    SVC3 --> LOKI
    
    SVC1 --> TEMPO
    SVC2 --> TEMPO
    SVC3 --> TEMPO
    
    PROM --> METRICS
    LOKI --> LOGS
    TEMPO --> TRACES
    
    METRICS --> GRAF
    LOGS --> GRAF
    TRACES --> GRAF
    
    GRAF --> ALERT
    ALERT --> SLACK
    ALERT --> EMAIL
    ALERT --> PAGER
```

---

## 10. DISASTER RECOVERY

```mermaid
graph TB
    subgraph "Primary Region"
        subgraph "Production"
            PROD_APP[Applications]
            PROD_DB[(Primary DB)]
            PROD_FILES[File Storage]
        end
    end
    
    subgraph "Backup Strategy"
        SYNC[Real-time Sync]
        SNAP[Hourly Snapshots]
        DAILY[Daily Backups]
    end
    
    subgraph "Secondary Region"
        subgraph "DR Site"
            DR_APP[Standby Apps]
            DR_DB[(Replica DB)]
            DR_FILES[File Mirror]
        end
    end
    
    subgraph "Recovery"
        FAIL[Failover]
        RESTORE[Restore]
        VALIDATE[Validation]
    end
    
    PROD_DB --> SYNC
    SYNC --> DR_DB
    
    PROD_DB --> SNAP
    SNAP --> DR_DB
    
    PROD_FILES --> DAILY
    DAILY --> DR_FILES
    
    PROD_APP -.-> FAIL
    FAIL -.-> DR_APP
    
    DR_DB --> RESTORE
    DR_FILES --> RESTORE
    RESTORE --> VALIDATE
    
    style PROD_APP fill:#9f9,stroke:#333,stroke-width:2px
    style DR_APP fill:#ff9,stroke:#333,stroke-width:2px
    style FAIL fill:#f99,stroke:#333,stroke-width:2px
```

---

## LEGEND

```mermaid
graph LR
    SYNC[Synchronous Call]
    ASYNC[Asynchronous Call]
    DATA[Data Flow]
    EVENT[Event Flow]
    
    A --> B
    C -.-> D
    E ==> F
    G -.-> H
    
    style SYNC fill:#9cf,stroke:#333
    style ASYNC fill:#fc9,stroke:#333
    style DATA fill:#9fc,stroke:#333
    style EVENT fill:#f9c,stroke:#333
```

**Обозначения:**
- `-->` Синхронное взаимодействие
- `-.->` Асинхронное взаимодействие
- `==>` Поток данных
- `[( )]` База данных
- `[ ]` Сервис/Компонент
- `{ }` Внешняя система

---

**📝 Документ подготовлен**: Claude Code Assistant  
**📅 Дата**: 18 сентября 2025  
**🔄 Версия**: 1.0.0