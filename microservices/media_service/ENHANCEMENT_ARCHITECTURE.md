# 🏗️ Media Service Enhancement Architecture

## 📅 Дата: 6 октября 2025

---

## 🎯 Архитектура предлагаемых улучшений

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          MEDIA SERVICE ENHANCED ARCHITECTURE                    │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   WEB CLIENT    │    │  MOBILE CLIENT  │    │  TELEGRAM BOT   │
│  (Dashboard)    │    │   (Future)      │    │   (Existing)    │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────▼──────────────┐
                    │     FASTAPI GATEWAY        │
                    │  (Enhanced with new APIs)  │
                    └─────────────┬──────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
┌─────────▼───────┐    ┌─────────▼───────┐    ┌─────────▼───────┐
│ IMAGE PROCESSOR │    │   AI TAGGER     │    │DUPLICATE DETECTOR│
│   Service       │    │   Service       │    │   Service       │
│                 │    │                 │    │                 │
│ • Compression   │    │ • Auto-tagging  │    │ • Hash check    │
│ • Thumbnails    │    │ • AI analysis   │    │ • Visual sim    │
│ • Format conv   │    │ • Fallback tags │    │ • Deduplication │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────▼──────────────┐
                    │   MEDIA STORAGE SERVICE    │
                    │     (Enhanced Core)        │
                    └─────────────┬──────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
┌─────────▼───────┐    ┌─────────▼───────┐    ┌─────────▼───────┐
│BACKUP SERVICE   │    │ANALYTICS SERVICE│    │NOTIFICATION     │
│                 │    │                 │    │SERVICE          │
│ • Scheduled     │    │ • Usage reports │    │                 │
│ • Priority-based│    │ • Trends        │    │ • Media alerts  │
│ • Multi-channel │    │ • Compression   │    │ • Priority-based│
│ • Monitoring    │    │   stats         │    │ • Templates     │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────▼──────────────┐
                    │    EXTERNAL SERVICES       │
                    │                            │
                    │ • AI Service (Vision)      │
                    │ • Notification Service     │
                    │ • User Service             │
                    │ • Request Service          │
                    └────────────────────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
┌─────────▼───────┐    ┌─────────▼───────┐    ┌─────────▼───────┐
│   POSTGRESQL    │    │     REDIS       │    │TELEGRAM CHANNELS│
│   (Enhanced)    │    │   (Enhanced)    │    │   (Enhanced)    │
│                 │    │                 │    │                 │
│ • Media files   │    │ • Cache         │    │ • Requests      │
│ • Compression   │    │ • Thumbnails    │    │ • Reports       │
│   metadata      │    │ • Analytics     │    │ • Archive       │
│ • Backup info   │    │ • Sessions      │    │ • Backup        │
│ • Analytics     │    │ • Rate limiting │    │ • Thumbnails    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

## 🔄 Enhanced Data Flow

### 📤 Upload Flow (Enhanced)

```
1. CLIENT UPLOAD
   ↓
2. VALIDATION (existing)
   ↓
3. DUPLICATE CHECK (NEW)
   ├─ Hash comparison
   ├─ Visual similarity (for images)
   └─ Decision: reuse/reject/warn
   ↓
4. IMAGE PROCESSING (NEW)
   ├─ Compression (if enabled)
   ├─ Thumbnail generation
   └─ Format optimization
   ↓
5. AI TAGGING (NEW)
   ├─ AI Service analysis
   ├─ Fallback tagging
   └─ Confidence scoring
   ↓
6. TELEGRAM UPLOAD (existing)
   ├─ Original file
   └─ Thumbnail (if image)
   ↓
7. DATABASE STORAGE (enhanced)
   ├─ Media metadata
   ├─ Compression info
   ├─ AI tags
   └─ Duplicate info
   ↓
8. NOTIFICATIONS (NEW)
   ├─ Recipients determination
   ├─ Priority calculation
   └─ Send alerts
   ↓
9. BACKUP SCHEDULING (NEW)
   ├─ Priority assessment
   ├─ Schedule backup
   └─ Update backup info
```

### 🔍 Search Flow (Enhanced)

```
1. SEARCH REQUEST
   ↓
2. CACHE CHECK (Redis)
   ├─ Query hash lookup
   └─ Return if cached
   ↓
3. DATABASE QUERY (enhanced)
   ├─ Full-text search
   ├─ Tag filtering
   ├─ AI tag search
   ├─ Date range
   └─ Similarity search
   ↓
4. RESULTS PROCESSING
   ├─ Thumbnail URLs
   ├─ Compression info
   ├─ Similarity scores
   └─ Relevance ranking
   ↓
5. CACHE STORAGE (Redis)
   ↓
6. RESPONSE TO CLIENT
```

---

## 🎯 Service Integration Map

### 🔗 Internal Services

```
Media Service Core
├── ImageProcessor
│   ├── Compression Engine
│   ├── Thumbnail Generator
│   └── Format Converter
│
├── AITagger
│   ├── AI Service Client
│   ├── Fallback Tagger
│   └── Confidence Scorer
│
├── DuplicateDetector
│   ├── Hash Calculator
│   ├── Visual Similarity
│   └── Decision Engine
│
├── BackupService
│   ├── Scheduler
│   ├── Channel Manager
│   └── Priority Handler
│
├── AnalyticsService
│   ├── Report Generator
│   ├── Trend Analyzer
│   └── Metrics Collector
│
└── NotificationService
    ├── Recipient Resolver
    ├── Template Engine
    └── Priority Manager
```

### 🌐 External Dependencies

```
External Services
├── AI Service (:8005)
│   ├── Vision Analysis
│   ├── Object Detection
│   └── Scene Recognition
│
├── Notification Service (:8006)
│   ├── Email/SMS/Push
│   ├── Template Engine
│   └── Delivery Tracking
│
├── User Service (:8002)
│   ├── User Info
│   ├── Permissions
│   └── Preferences
│
├── Request Service (:8001)
│   ├── Request Details
│   ├── Participants
│   └── Status Updates
│
└── Telegram Bot API
    ├── File Upload
    ├── Channel Management
    └── Message Handling
```

---

## 📊 Enhanced Database Schema

### 🗃️ New Tables

```sql
-- Compression metadata
CREATE TABLE media_compression (
    id SERIAL PRIMARY KEY,
    media_file_id INTEGER REFERENCES media_files(id),
    original_size BIGINT NOT NULL,
    compressed_size BIGINT NOT NULL,
    compression_ratio DECIMAL(5,4) NOT NULL,
    algorithm VARCHAR(50) DEFAULT 'JPEG',
    quality INTEGER DEFAULT 85,
    processed_at TIMESTAMP DEFAULT NOW()
);

-- AI tagging results
CREATE TABLE media_ai_tags (
    id SERIAL PRIMARY KEY,
    media_file_id INTEGER REFERENCES media_files(id),
    tag_name VARCHAR(100) NOT NULL,
    confidence DECIMAL(5,4) NOT NULL,
    source VARCHAR(50) DEFAULT 'ai_service',
    ai_model VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Backup information
CREATE TABLE media_backups (
    id SERIAL PRIMARY KEY,
    original_media_id INTEGER REFERENCES media_files(id),
    backup_file_id VARCHAR(200) NOT NULL,
    backup_channel_id BIGINT NOT NULL,
    backup_timestamp TIMESTAMP DEFAULT NOW(),
    priority VARCHAR(20) DEFAULT 'normal',
    status VARCHAR(20) DEFAULT 'active'
);

-- Duplicate relationships
CREATE TABLE media_duplicates (
    id SERIAL PRIMARY KEY,
    original_file_id INTEGER REFERENCES media_files(id),
    duplicate_file_id INTEGER REFERENCES media_files(id),
    similarity_score DECIMAL(5,4),
    detection_method VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Analytics cache
CREATE TABLE media_analytics_cache (
    id SERIAL PRIMARY KEY,
    cache_key VARCHAR(200) UNIQUE NOT NULL,
    cache_data JSONB NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 🔄 Enhanced Existing Tables

```sql
-- Add new columns to media_files
ALTER TABLE media_files ADD COLUMN compression_ratio DECIMAL(5,4);
ALTER TABLE media_files ADD COLUMN original_size BIGINT;
ALTER TABLE media_files ADD COLUMN thumbnail_file_id VARCHAR(200);
ALTER TABLE media_files ADD COLUMN backup_file_id VARCHAR(200);
ALTER TABLE media_files ADD COLUMN file_hash VARCHAR(64);
ALTER TABLE media_files ADD COLUMN ai_confidence DECIMAL(5,4);
ALTER TABLE media_files ADD COLUMN processing_status VARCHAR(20) DEFAULT 'ready';
```

---

## 🚀 Deployment Architecture

### 🐳 Enhanced Docker Compose

```yaml
version: '3.8'

services:
  media-service:
    build: .
    ports:
      - "8004:8004"
    environment:
      # Existing config
      - DATABASE_URL=postgresql+asyncpg://media_user:media_pass@media-db:5432/media_db
      - REDIS_URL=redis://shared-redis:6379/4
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      
      # New config
      - ENABLE_COMPRESSION=true
      - ENABLE_AI_TAGGING=true
      - ENABLE_DUPLICATE_DETECTION=true
      - ENABLE_BACKUP=true
      - AI_SERVICE_URL=http://ai-service:8005
      - NOTIFICATION_SERVICE_URL=http://notification-service:8006
      
      # Compression settings
      - MAX_IMAGE_DIMENSIONS=1920x1080
      - JPEG_QUALITY=85
      - THUMBNAIL_SIZE=300x300
      
      # Backup settings
      - BACKUP_SCHEDULE=0 2 * * *  # Daily at 2 AM
      - BACKUP_RETENTION_DAYS=365
      
    depends_on:
      - media-db
      - shared-redis
      - ai-service
      - notification-service

  # Enhanced Redis with additional databases
  shared-redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes --maxmemory 512mb
    ports:
      - "6379:6379"

  # New: Dedicated Redis for thumbnails
  thumbnail-redis:
    image: redis:7-alpine
    volumes:
      - thumbnail-data:/data
    command: redis-server --appendonly yes --maxmemory 1gb
    ports:
      - "6380:6379"

volumes:
  redis-data:
  thumbnail-data:
```

### 📊 Monitoring Stack

```yaml
# Additional monitoring services
services:
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana-data:/var/lib/grafana

  # Enhanced metrics for Media Service
  media-exporter:
    build: ./monitoring/media-exporter
    environment:
      - MEDIA_SERVICE_URL=http://media-service:8004
      - PROMETHEUS_GATEWAY=http://prometheus:9090
```

---

## 🔧 Configuration Management

### ⚙️ Enhanced Settings

```python
# app/core/enhanced_config.py
class EnhancedSettings(Settings):
    # Image Processing
    enable_compression: bool = True
    max_image_dimensions: tuple = (1920, 1080)
    jpeg_quality: int = 85
    thumbnail_size: tuple = (300, 300)
    compression_algorithms: List[str] = ["JPEG", "WebP"]
    
    # AI Integration
    enable_ai_tagging: bool = True
    ai_service_url: str = "http://ai-service:8005"
    ai_confidence_threshold: float = 0.7
    fallback_tagging: bool = True
    
    # Duplicate Detection
    enable_duplicate_detection: bool = True
    similarity_threshold: float = 0.95
    hash_algorithms: List[str] = ["md5", "sha256"]
    
    # Backup Configuration
    enable_backup: bool = True
    backup_schedule: str = "0 2 * * *"  # Daily at 2 AM
    backup_retention_days: int = 365
    backup_channels: Dict[str, str] = {
        "primary": "-1002951349061",
        "secondary": "-1002951349062"
    }
    
    # Analytics
    enable_analytics: bool = True
    analytics_cache_ttl: int = 3600
    report_generation_enabled: bool = True
    
    # Notifications
    enable_notifications: bool = True
    notification_service_url: str = "http://notification-service:8006"
    notification_priorities: Dict[str, str] = {
        "critical": "high",
        "important": "medium", 
        "normal": "low"
    }
```

---

## 📈 Performance Considerations

### ⚡ Optimization Strategies

1. **Async Processing Pipeline**:
   ```
   Upload → Validation → Queue → Process → Store → Notify
   ```

2. **Caching Strategy**:
   ```
   Redis Layers:
   ├── L1: Thumbnails (1GB)
   ├── L2: Search Results (512MB)
   ├── L3: Analytics Data (256MB)
   └── L4: Session Data (128MB)
   ```

3. **Background Tasks**:
   ```
   Celery Tasks:
   ├── Image Processing
   ├── AI Tagging
   ├── Backup Operations
   ├── Analytics Generation
   └── Cleanup Tasks
   ```

4. **Database Optimization**:
   ```
   Indexes:
   ├── file_hash (unique)
   ├── compression_ratio
   ├── ai_confidence
   ├── backup_timestamp
   └── similarity_score
   ```

---

## 🎯 Implementation Timeline

### 📅 Phase 1: Core Enhancements (Weeks 1-3)

```
Week 1: Image Processing
├── ImageProcessor implementation
├── Compression engine
├── Thumbnail generation
└── Integration testing

Week 2: AI Integration  
├── AITagger service
├── AI Service integration
├── Fallback tagging
└── Confidence scoring

Week 3: Duplicate Detection
├── DuplicateDetector implementation
├── Hash-based detection
├── Visual similarity
└── Decision engine
```

### 📅 Phase 2: User Experience (Weeks 4-6)

```
Week 4-5: Web Dashboard
├── Frontend development
├── Gallery implementation
├── Search interface
└── Real-time updates

Week 6: Integration
├── API integration
├── Performance optimization
├── User testing
└── Bug fixes
```

### 📅 Phase 3: Advanced Features (Weeks 7-10)

```
Week 7-8: Analytics & Reports
├── AnalyticsService implementation
├── Report generation
├── Trend analysis
└── Dashboard integration

Week 9-10: Backup & Notifications
├── BackupService implementation
├── NotificationService integration
├── Scheduled tasks
└── Monitoring setup
```

---

## ✅ Success Metrics

### 📊 Key Performance Indicators

1. **Performance**:
   - 📉 File size reduction: 60-80%
   - ⚡ Upload speed improvement: 40-60%
   - 🔄 Processing time: <2s per image

2. **Quality**:
   - 🎯 Auto-tagging accuracy: >90%
   - 🔍 Search relevance: >85%
   - 💾 Backup coverage: 100%

3. **User Experience**:
   - 👥 User satisfaction: >4.5/5
   - 📱 Mobile compatibility: 100%
   - 🚀 Feature adoption: >80%

4. **Reliability**:
   - 🛡️ Uptime: >99.9%
   - 🔄 Error rate: <0.1%
   - 📊 Data consistency: 100%

---

*Архитектурный документ подготовлен: 6 октября 2025*  
*Статус: Готов к техническому review*

