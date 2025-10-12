# 🏗️ Архитектурные диаграммы UK Management Bot

## Основная архитектурная схема

```mermaid
graph TB
    %% Frontend Layer
    subgraph Frontend["🖥️ Frontend Applications"]
        WebApp["🌐 WebApp<br/>React/Vue SPA<br/>Port: 3000"]
        TgBot["💬 Telegram Bot<br/>Webhook/Polling"]
        AdminPanel["📊 Admin Panel<br/>Dashboards<br/>Port: 3001"]
    end

    %% API Gateway
    Gateway["🔀 API Gateway<br/>Nginx/Traefik<br/>Load Balancer"]

    %% Backend Services
    subgraph Services["⚙️ Backend Services"]
        Core["🔐 Core Service<br/>Auth/Users/Requests<br/>📍 Building Assets<br/>Port: 8001"]
        Ops["📅 Operations Service<br/>Shifts/Scheduling<br/>Port: 8002"]
        Comm["📤 Communication Hub<br/>Notifications/WebSocket<br/>Port: 8003"]
        Media["📁 Media Storage<br/>Files/CDN<br/>Port: 8004"]
        Analytics["📊 Analytics Service<br/>KPIs/Reports<br/>Port: 8005"]
        Integration["📥 Integration Hub<br/>External APIs<br/>Port: 8006"]
        AI["🤖 AI/ML Service<br/>[FUTURE]<br/>Port: 8007"]
    end

    %% Message Queue
    subgraph MQ["🐰 Message Queue Infrastructure"]
        RabbitMQ["RabbitMQ Broker<br/>Port: 5672"]

        subgraph Queues["Priority Queues"]
            HighQ["🔴 HIGH (9-10)<br/>comm.urgent<br/>ops.emergency"]
            MedQ["🟡 MEDIUM (4-8)<br/>core.tasks<br/>media.upload"]
            LowQ["🟢 LOW (1-3)<br/>analytics.batch<br/>comm.batch"]
            DLQ["☠️ Dead Letter Queue"]
        end
    end

    %% Workers
    subgraph Workers["👷 Celery Workers"]
        CoreWorker["core-worker x3"]
        OpsWorker["ops-worker x2"]
        CommWorker["comm-worker x5"]
        MediaWorker["media-worker x3"]
        AnalyticsWorker["analytics-worker x2"]
        IntegrationWorker["integration-worker x3"]
    end

    %% Data Storage
    subgraph Storage["💾 Data Storage"]
        PostgreSQL["🐘 PostgreSQL<br/>7 Databases"]
        Redis["⚡ Redis<br/>Cache & Sessions<br/>Port: 6379"]
        S3["☁️ S3/MinIO<br/>File Storage"]
    end

    %% Monitoring
    subgraph Monitoring["📈 Monitoring"]
        Prometheus["Prometheus<br/>Port: 9090"]
        Grafana["Grafana<br/>Port: 3000"]
        Flower["Flower<br/>Port: 5555"]
    end

    %% Connections - User Flow
    WebApp --> Gateway
    TgBot --> Gateway
    AdminPanel --> Gateway
    Gateway --> Core
    Gateway --> Ops
    Gateway --> Comm
    Gateway --> Media
    Gateway --> Analytics
    Gateway --> Integration

    %% Service to Service
    Core -.->|Auth Check| Ops
    Core -.->|User Data| Comm
    Core -.->|Building/Location Data| Ops
    Ops -.->|Assignment| Core
    Integration -.->|External Building Data| Core
    Media -.->|File URLs| Core
    Analytics -.->|Read Events| Redis

    %% Queue Publishing
    Core -->|Publish| RabbitMQ
    Ops -->|Publish| RabbitMQ
    Comm -->|Publish| RabbitMQ
    Media -->|Publish| RabbitMQ
    Analytics -->|Publish| RabbitMQ
    Integration -->|Publish| RabbitMQ

    %% Queue Distribution
    RabbitMQ --> HighQ
    RabbitMQ --> MedQ
    RabbitMQ --> LowQ
    HighQ --> DLQ
    MedQ --> DLQ
    LowQ --> DLQ

    %% Workers Consuming
    HighQ --> CommWorker
    HighQ --> OpsWorker
    MedQ --> CoreWorker
    MedQ --> MediaWorker
    MedQ --> IntegrationWorker
    LowQ --> AnalyticsWorker

    %% Data Persistence
    Core --> PostgreSQL
    Ops --> PostgreSQL
    Comm --> PostgreSQL
    Media --> PostgreSQL
    Analytics --> PostgreSQL
    Integration --> PostgreSQL
    AI -.->|Future| PostgreSQL

    %% Cache Layer
    Core --> Redis
    Ops --> Redis
    Comm --> Redis
    Media --> Redis
    Analytics --> Redis
    Integration --> Redis

    %% File Storage
    Media --> S3

    %% WebSocket
    Comm -.->|WebSocket| WebApp

    %% Monitoring
    Services -.->|Metrics| Prometheus
    Prometheus --> Grafana
    RabbitMQ -.->|Queue Stats| Flower

    %% Styling
    classDef frontend fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef service fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef queue fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef storage fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    classDef monitor fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    classDef future fill:#f5f5f5,stroke:#9e9e9e,stroke-width:2px,stroke-dasharray: 5 5

    class WebApp,TgBot,AdminPanel frontend
    class Core,Ops,Comm,Media,Analytics,Integration service
    class RabbitMQ,HighQ,MedQ,LowQ,DLQ queue
    class PostgreSQL,Redis,S3 storage
    class Prometheus,Grafana,Flower monitor
    class AI future
```

## Схема потоков данных (Sequence Diagram)

```mermaid
sequenceDiagram
    participant U as User/WebApp
    participant G as API Gateway
    participant C as Core Service
    participant Q as RabbitMQ
    participant W as Celery Worker
    participant R as Redis
    participant I as Integration Hub
    participant N as Communication Hub

    U->>G: Create Request
    G->>C: POST /api/v1/requests

    Note over C: Validate & Save
    C->>Q: Publish task<br/>"assign_executor"
    C-->>U: 202 Accepted<br/>{"task_id": "123"}

    Note over Q,W: Async Processing
    Q->>W: Consume task
    W->>I: Get building data
    I-->>W: Building info
    W->>W: Calculate assignment
    W->>R: Store result

    W->>Q: Publish task<br/>"send_notification"
    Q->>N: Notify executor
    N->>N: Send Telegram/Email

    U->>C: GET /api/v1/tasks/123
    C->>R: Check result
    R-->>C: Task result
    C-->>U: Assignment completed
```

## Схема приоритетов очередей

```mermaid
flowchart LR
    subgraph Services
        S1[Services]
    end

    subgraph RabbitMQ
        direction TB
        E1[Exchange]
        Q1[🔴 Priority 9-10<br/>Urgent Tasks]
        Q2[🟡 Priority 4-8<br/>Normal Tasks]
        Q3[🟢 Priority 1-3<br/>Batch Tasks]
        DLQ[☠️ DLQ<br/>Failed Tasks]

        E1 --> Q1
        E1 --> Q2
        E1 --> Q3
        Q1 -.->|Max Retries| DLQ
        Q2 -.->|Max Retries| DLQ
        Q3 -.->|Max Retries| DLQ
    end

    subgraph Workers
        W1[High Priority<br/>Workers x5]
        W2[Medium Priority<br/>Workers x8]
        W3[Low Priority<br/>Workers x2]
        WD[DLQ Handler]
    end

    S1 -->|Publish| E1
    Q1 -->|Consume| W1
    Q2 -->|Consume| W2
    Q3 -->|Consume| W3
    DLQ -->|Process| WD

    style Q1 fill:#fee,stroke:#f00
    style Q2 fill:#ffe,stroke:#fa0
    style Q3 fill:#efe,stroke:#0a0
    style DLQ fill:#eee,stroke:#000
```

## Архитектура сервисов (C4 Context)

```mermaid
C4Context
    title System Context - UK Management Bot

    Person(user, "User", "Пользователь системы")
    Person(executor, "Executor", "Исполнитель заявок")
    Person(admin, "Admin", "Администратор")

    System_Boundary(uk_system, "UK Management System") {
        System(webapp, "WebApp", "React SPA")
        System(telegram, "Telegram Bot", "Bot Interface")
        System(backend, "Backend Services", "7 Microservices")
        System(queue, "Message Queue", "RabbitMQ + Celery")
    }

    System_Ext(google, "Google Services", "Sheets, Maps")
    System_Ext(yandex, "Yandex Maps", "Geocoding")
    System_Ext(building_api, "Building Directory", "External API")
    System_Ext(telegram_api, "Telegram API", "Messaging")

    Rel(user, webapp, "Uses", "HTTPS")
    Rel(user, telegram, "Uses", "Messages")
    Rel(executor, telegram, "Uses", "Commands")
    Rel(admin, webapp, "Manages", "HTTPS")

    Rel(webapp, backend, "API calls", "REST/WebSocket")
    Rel(telegram, backend, "Webhook/Polling", "HTTPS")
    Rel(backend, queue, "Publishes tasks", "AMQP")

    Rel(backend, google, "Sync data", "API")
    Rel(backend, yandex, "Geocoding", "API")
    Rel(backend, building_api, "Get buildings", "REST")
    Rel(telegram, telegram_api, "Send messages", "API")
```

## Deployment Diagram

```mermaid
graph TB
    subgraph Docker["🐋 Docker Compose Environment"]
        subgraph Services["Services Network"]
            CS[Core Service<br/>Container]
            OS[Operations Service<br/>Container]
            CH[Communication Hub<br/>Container]
            MS[Media Storage<br/>Container]
            AS[Analytics Service<br/>Container]
            IH[Integration Hub<br/>Container]
        end

        subgraph Infrastructure["Infrastructure"]
            RMQ[RabbitMQ<br/>Container]
            REDIS[Redis<br/>Container]

            subgraph DBs["PostgreSQL Instances"]
                DB1[(core_db)]
                DB2[(ops_db)]
                DB3[(comm_db)]
                DB4[(media_db)]
                DB5[(analytics_db)]
                DB6[(integration_db)]
                DB7[(ai_db)]
            end
        end

        subgraph Workers["Celery Workers"]
            CW1[core-worker-1]
            CW2[core-worker-2]
            CW3[core-worker-3]
            OW[ops-workers]
            CMW[comm-workers]
            MW[media-workers]
            AW[analytics-workers]
            IW[integration-workers]
        end

        subgraph Frontend["Frontend"]
            WEB[WebApp<br/>nginx]
            ADMIN[Admin Panel<br/>nginx]
        end
    end

    subgraph External["External Services"]
        TG[Telegram API]
        GAPI[Google APIs]
        YAPI[Yandex APIs]
        BAPI[Building API]
    end

    CS --> DB1
    OS --> DB2
    CH --> DB3
    MS --> DB4
    AS --> DB5
    IH --> DB6

    Services --> RMQ
    Services --> REDIS
    RMQ --> Workers
    Workers --> REDIS

    IH --> GAPI
    IH --> YAPI
    IH --> BAPI
    CH --> TG
```

## Data Flow для создания заявки

```mermaid
graph LR
    subgraph User["User Action"]
        U[User creates request]
    end

    subgraph CoreService["Core Service"]
        CS1[Validate request]
        CS2[Generate request_number]
        CS2A[Get building/location]
        CS3[Save to DB]
        CS4[Publish task]
    end

    subgraph Queue["RabbitMQ"]
        Q1[core.tasks queue]
        Q2[ops.assignment queue]
        Q3[comm.urgent queue]
    end

    subgraph Workers["Celery Workers"]
        W1[Fetch building data]
        W2[Calculate assignment]
        W3[Send notifications]
    end

    subgraph External["External Services"]
        IH[Integration Hub]
        CH[Communication Hub]
    end

    U --> CS1
    CS1 --> CS2
    CS2 --> CS2A
    CS2A --> CS3
    CS3 --> CS4
    CS4 --> Q1

    Q1 --> W1
    W1 --> IH
    IH --> W1
    W1 --> Q2

    Q2 --> W2
    W2 --> Q3

    Q3 --> W3
    W3 --> CH
    CH --> U

    style U fill:#e1f5fe
    style CS1,CS2,CS3,CS4 fill:#fff3e0
    style Q1,Q2,Q3 fill:#f3e5f5
    style W1,W2,W3 fill:#e8f5e9
```

## Service Dependencies

```mermaid
graph TD
    subgraph Layer1["Layer 1: Core Infrastructure"]
        AUTH[Auth in Core Service]
        REDIS[Redis Cache]
        PG[PostgreSQL]
    end

    subgraph Layer2["Layer 2: Business Services"]
        CORE[Core Service]
        OPS[Operations Service]
        MEDIA[Media Storage]
    end

    subgraph Layer3["Layer 3: Integration Layer"]
        COMM[Communication Hub]
        INT[Integration Hub]
        ANALYTICS[Analytics Service]
    end

    subgraph Layer4["Layer 4: Optional"]
        AI[AI/ML Service]
    end

    CORE --> AUTH
    CORE --> REDIS
    CORE --> PG

    OPS --> CORE
    OPS --> REDIS
    OPS --> PG

    MEDIA --> REDIS
    MEDIA --> PG

    COMM --> CORE
    COMM --> REDIS
    INT --> CORE
    INT --> REDIS

    ANALYTICS --> REDIS
    ANALYTICS --> PG

    AI -.-> OPS
    AI -.-> REDIS

    style AI fill:#f5f5f5,stroke:#9e9e9e,stroke-width:2px,stroke-dasharray: 5 5
```

## Monitoring Architecture

```mermaid
graph TD
    subgraph Services["Microservices"]
        S1[Core Service]
        S2[Operations Service]
        S3[Communication Hub]
        S4[Media Storage]
        S5[Analytics Service]
        S6[Integration Hub]
    end

    subgraph Metrics["Metrics Collection"]
        PROM[Prometheus<br/>:9090]
        METRICS[/metrics endpoints]
    end

    subgraph Visualization["Visualization"]
        GRAF[Grafana<br/>:3000]
        DASH1[System Dashboard]
        DASH2[Business KPIs]
        DASH3[Queue Metrics]
    end

    subgraph Queues["Queue Monitoring"]
        FLOWER[Flower<br/>:5555]
        RMQ_UI[RabbitMQ Management<br/>:15672]
    end

    subgraph Alerts["Alerting"]
        AM[AlertManager]
        SLACK[Slack]
        EMAIL[Email]
    end

    Services --> METRICS
    METRICS --> PROM
    PROM --> GRAF
    GRAF --> DASH1
    GRAF --> DASH2
    GRAF --> DASH3

    Services --> FLOWER
    Services --> RMQ_UI

    PROM --> AM
    AM --> SLACK
    AM --> EMAIL
```

## Network Architecture

```mermaid
graph TB
    subgraph Internet
        USERS[Users]
        TG_API[Telegram API]
        EXT_API[External APIs]
    end

    subgraph DMZ["DMZ"]
        LB[Load Balancer<br/>Nginx/Traefik]
        WAF[Web Application<br/>Firewall]
    end

    subgraph AppTier["Application Tier"]
        GW[API Gateway]
        WEB[WebApp]
        ADMIN[Admin Panel]
    end

    subgraph ServiceTier["Service Tier - Docker Network"]
        CORE[Core Service :8001]
        OPS[Operations :8002]
        COMM[Communication :8003]
        MEDIA[Media :8004]
        ANALYTICS[Analytics :8005]
        INTEGRATION[Integration :8006]
    end

    subgraph DataTier["Data Tier"]
        PG[(PostgreSQL)]
        REDIS[(Redis)]
        RMQ[RabbitMQ]
        S3[S3/MinIO]
    end

    USERS --> WAF
    WAF --> LB
    LB --> GW
    GW --> WEB
    GW --> ADMIN

    WEB --> ServiceTier
    ADMIN --> ServiceTier

    ServiceTier --> DataTier

    COMM <--> TG_API
    INTEGRATION <--> EXT_API

    style ServiceTier fill:#fff3e0
    style DataTier fill:#e8f5e9
```

## Building Assets Module Architecture

```mermaid
graph TB
    subgraph CoreService["🔐 Core Service"]
        subgraph BuildingAssets["📍 Building Assets Module"]
            BA_API["Asset API<br/>Endpoints"]
            BA_Service["Asset Service<br/>Business Logic"]
            BA_Geo["Geo Service<br/>PostGIS"]
            BA_Cache["Cache Layer<br/>Redis"]
        end

        subgraph CoreModules["Core Modules"]
            Auth["Auth Module"]
            Users["Users Module"]
            Requests["Requests Module"]
        end
    end

    subgraph DataModel["Data Model"]
        Complex["Complex<br/>(Жилой комплекс)"]
        Building["Building<br/>(Здание)"]
        Entrance["Entrance<br/>(Подъезд)"]
        Floor["Floor<br/>(Этаж)"]
        Apartment["Apartment<br/>(Квартира)"]
        Parking["Parking<br/>(Парковка)"]
    end

    subgraph GeoDB["🌍 Geo Database (PostGIS)"]
        Points["Points<br/>(Coordinates)"]
        Polygons["Polygons<br/>(Boundaries)"]
        Zones["Service Zones"]
    end

    subgraph Integration["Integrations"]
        Ops_Service["Operations Service<br/>(Route Optimization)"]
        Int_Hub["Integration Hub<br/>(External Building APIs)"]
        Analytics["Analytics Service<br/>(Location Analytics)"]
    end

    %% Internal connections
    BA_API --> BA_Service
    BA_Service --> BA_Geo
    BA_Service --> BA_Cache
    BA_Geo --> GeoDB

    %% Core module connections
    Users -.->|Resident Address| BA_Service
    Requests -.->|Request Location| BA_Service
    Auth -.->|Location Access Control| BA_Service

    %% Data hierarchy
    Complex --> Building
    Building --> Entrance
    Entrance --> Floor
    Floor --> Apartment
    Building --> Parking

    %% External service connections
    BA_Service --> Ops_Service
    Int_Hub --> BA_Service
    BA_Service --> Analytics

    %% Geo connections
    Building --> Points
    Complex --> Polygons
    Zones --> Polygons

    style BuildingAssets fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style GeoDB fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style DataModel fill:#fff3e0,stroke:#ef6c00,stroke-width:2px
```

## Building Assets API Flow

```mermaid
sequenceDiagram
    participant U as User
    participant API as Core Service API
    participant BAM as Building Assets Module
    participant GEO as PostGIS
    participant CACHE as Redis Cache
    participant INT as Integration Hub

    U->>API: Create Request<br/>(apartment_id: 256)
    API->>BAM: Get apartment location

    alt Cache Hit
        BAM->>CACHE: Check cache
        CACHE-->>BAM: Location data
    else Cache Miss
        BAM->>GEO: Query spatial data
        GEO-->>BAM: Coordinates & zone
        BAM->>CACHE: Update cache
    end

    BAM-->>API: Location: [55.747, 37.537]<br/>Zone: "Zone-A"

    API->>API: Attach location to request
    API->>BAM: Find nearby executors
    BAM->>GEO: ST_DWithin query
    GEO-->>BAM: Nearby buildings list
    BAM-->>API: Buildings in 5km radius

    API-->>U: Request created with geo-data

    Note over INT,BAM: Periodic sync
    INT->>BAM: Update building registry
    BAM->>GEO: Upsert building data
```

## Service Dependencies Graph

```mermaid
graph TB
    %% Frontend Layer
    subgraph Frontend["🖥️ Frontend Layer"]
        WebApp["🌐 WebApp<br/>React/Vue SPA"]
        TgBot["💬 Telegram Bot<br/>Commands/Menus"]
        AdminPanel["📊 Admin Panel<br/>Monitoring"]
    end

    %% API Gateway
    Gateway["🔀 API Gateway<br/>Load Balancer"]

    %% Core Services
    subgraph CoreServices["⚙️ Core Services"]
        Core["🔐 Core Service<br/>Auth/Users/Requests<br/>📍 Building Assets"]
        Ops["📅 Operations Service<br/>Shifts/Assignments"]
        Comm["📤 Communication Hub<br/>Notifications"]
    end

    %% Support Services
    subgraph SupportServices["🔧 Support Services"]
        Media["📁 Media Storage<br/>Files/CDN"]
        Analytics["📊 Analytics Service<br/>Reports/KPIs"]
        Integration["📥 Integration Hub<br/>External APIs"]
    end

    %% Optional Services
    subgraph Optional["🔮 Optional Services"]
        AI["🤖 AI/ML Service<br/>[FUTURE]<br/>Optimization"]
    end

    %% Critical Dependencies (solid lines)
    Frontend --> Gateway
    Gateway --> Core

    Ops -->|"Critical:<br/>Request data"| Core
    Comm -->|"Critical:<br/>User data"| Core
    Analytics -->|"Critical:<br/>Base data"| Core
    AI -->|"Critical:<br/>Historical data"| Core
    AI -->|"Critical:<br/>Current state"| Ops
    TgBot -->|"Critical:<br/>Commands"| Comm
    TgBot -->|"Critical:<br/>Auth"| Core

    %% Optional Dependencies (dashed lines)
    Core -.->|"Optional:<br/>Events"| Analytics
    Core -.->|"Optional:<br/>External data"| Integration
    Ops -.->|"Optional:<br/>AI optimization"| AI
    Ops -.->|"Optional:<br/>Geo data"| Integration
    Comm -.->|"Optional:<br/>Media files"| Media
    Integration -.->|"Optional:<br/>Building updates"| Core

    %% Styling
    classDef critical fill:#ffebee,stroke:#c62828,stroke-width:2px
    classDef optional fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px,stroke-dasharray: 5 5
    classDef independent fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px

    class Core,Ops,Comm critical
    class AI optional
    class Media,Integration,Analytics independent
```

## Service Dependencies Matrix

```mermaid
graph LR
    subgraph Matrix["Dependencies Impact Matrix"]
        subgraph HighImpact["🔴 High Impact if Failed"]
            Core_Impact["Core Service<br/>• Operations stops<br/>• Communication stops<br/>• AI/ML stops<br/>• Analytics degraded"]
        end

        subgraph MediumImpact["🟡 Medium Impact if Failed"]
            Ops_Impact["Operations Service<br/>• No shift management<br/>• No assignments<br/>• Bot degraded"]
            Comm_Impact["Communication Hub<br/>• No notifications<br/>• Bot degraded<br/>• Delayed messages"]
        end

        subgraph LowImpact["🟢 Low/No Impact if Failed"]
            Media_Impact["Media Storage<br/>• No file uploads<br/>• Inline content only"]
            Analytics_Impact["Analytics Service<br/>• No reports<br/>• No dashboards"]
            Integration_Impact["Integration Hub<br/>• No external sync<br/>• Cache still works"]
            AI_Impact["AI/ML Service<br/>• Fallback to basic<br/>• Manual assignment"]
        end
    end

    style HighImpact fill:#ffcdd2
    style MediumImpact fill:#fff9c4
    style LowImpact fill:#c8e6c9
```

## Fallback Scenarios Flow

```mermaid
flowchart TD
    Start([Service Request])

    CheckAI{AI/ML Service<br/>Available?}
    CheckIntegration{Integration Hub<br/>Available?}
    CheckComm{Communication<br/>Available?}

    UseAI[Use AI Optimization<br/>500ms response]
    UseBasic[Use Basic Algorithm<br/>100ms response]

    UseGeoData[Use Real-time<br/>Geo Data]
    UseCachedGeo[Use Cached<br/>Geo Data<br/>TTL: 7 days]

    SendNotification[Send Push<br/>Notification]
    QueueNotification[Queue for<br/>Later Delivery]
    ShowInBot[Show in Bot<br/>Interface Only]

    Complete([Request Processed])

    Start --> CheckAI

    CheckAI -->|Yes| UseAI
    CheckAI -->|No| UseBasic

    UseAI --> CheckIntegration
    UseBasic --> CheckIntegration

    CheckIntegration -->|Yes| UseGeoData
    CheckIntegration -->|No| UseCachedGeo

    UseGeoData --> CheckComm
    UseCachedGeo --> CheckComm

    CheckComm -->|Yes| SendNotification
    CheckComm -->|No| QueueNotification
    CheckComm -->|Partial| ShowInBot

    SendNotification --> Complete
    QueueNotification --> Complete
    ShowInBot --> Complete

    style UseAI fill:#e3f2fd
    style UseBasic fill:#fff3e0
    style UseCachedGeo fill:#fff9c4
    style QueueNotification fill:#ffebee
```

## Service Startup Order

```mermaid
graph TD
    subgraph Infrastructure["1️⃣ Infrastructure Layer"]
        MQ[Message Queue<br/>RabbitMQ]
        Cache[Redis Cache]
        DB[PostgreSQL<br/>Databases]
    end

    subgraph Independent["2️⃣ Independent Services"]
        MediaSvc[Media Storage]
        IntegrationSvc[Integration Hub]
    end

    subgraph Critical["3️⃣ Critical Services"]
        CoreSvc[Core Service<br/>+Building Assets]
    end

    subgraph Dependent["4️⃣ Dependent Services"]
        OpsSvc[Operations Service]
        CommSvc[Communication Hub]
        AnalyticsSvc[Analytics Service]
    end

    subgraph Frontend["5️⃣ Frontend Applications"]
        Bot[Telegram Bot]
        Web[WebApp]
        Admin[Admin Panel]
    end

    subgraph Optional["6️⃣ Optional Services"]
        AISvc[AI/ML Service]
    end

    MQ --> Cache
    Cache --> DB
    DB --> MediaSvc
    DB --> IntegrationSvc
    DB --> CoreSvc

    CoreSvc --> OpsSvc
    CoreSvc --> CommSvc
    CoreSvc --> AnalyticsSvc

    CommSvc --> Bot
    CoreSvc --> Web
    CoreSvc --> Admin

    OpsSvc --> AISvc
    CoreSvc --> AISvc

    style Infrastructure fill:#e8f5e9
    style Independent fill:#fff3e0
    style Critical fill:#ffebee
    style Dependent fill:#e3f2fd
    style Frontend fill:#f3e5f5
    style Optional fill:#f5f5f5,stroke:#9e9e9e,stroke-dasharray: 5 5
```

## Critical Path Analysis

```mermaid
graph LR
    subgraph CriticalPath["🔴 Critical Path: Request Creation"]
        CP1[User Input] -->|1| CP2[Bot Gateway]
        CP2 -->|2| CP3[Core Service]
        CP3 -->|3| CP4[Building Assets]
        CP4 -->|4| CP5[Operations Service]
        CP5 -->|5| CP6[Assignment]
        CP6 -->|6| CP7[Communication Hub]
        CP7 -->|7| CP8[User Notification]
    end

    subgraph OptionalEnhancements["🟡 Optional Enhancements"]
        CP4 -.->|Optional| OE1[Integration Hub<br/>Fresh Geo Data]
        CP5 -.->|Optional| OE2[AI/ML Service<br/>Smart Assignment]
        CP7 -.->|Optional| OE3[Media Storage<br/>File Attachments]
    end

    subgraph Monitoring["🟢 Monitoring Path"]
        CP3 --> M1[Analytics Service<br/>Event Logging]
        CP5 --> M1
        CP7 --> M1
    end

    style CriticalPath fill:#ffebee
    style OptionalEnhancements fill:#fff9c4
    style Monitoring fill:#e8f5e9
```