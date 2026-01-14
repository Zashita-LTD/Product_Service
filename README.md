# Product Service (High-Load)

Высоконагруженный микросервис для управления товарными семействами с AI-обогащением.

## 🏗️ Архитектура

Проект построен на принципах **Clean Architecture** с четким разделением слоев:

```
product-service/
├── cmd/                    # Точки входа приложений
│   ├── api/               # REST API сервер (FastAPI)
│   ├── worker-enrichment/ # AI воркер (Gemini)
│   ├── worker-raw-products/ # Импорт товаров от Parser Service
│   ├── worker-sync/       # Sync воркер (Meilisearch)
│   └── migrator/          # DB миграции
├── internal/              # Внутренняя логика
│   ├── domain/           # Доменные сущности и ошибки
│   ├── usecase/          # Бизнес-логика
│   ├── infrastructure/   # Внешние сервисы (DB, Cache, Kafka)
│   └── transport/        # HTTP handlers
├── pkg/                   # Переиспользуемые пакеты
│   ├── logger/           # Структурированное логирование
│   └── resilience/       # Circuit Breaker, Rate Limiter
├── migrations/            # SQL миграции
├── deploy/               # Конфигурации деплоя
│   ├── docker/          # Docker файлы
│   └── helm/            # Kubernetes Helm чарты
└── tests/                # Тесты
```

## 🎯 Ключевые архитектурные решения

### 1. Outbox Pattern
Гарантированная доставка событий через паттерн Outbox:
- Запись в `product_families` и `outbox_events` в одной транзакции
- Отдельный процесс публикует события в Kafka
- Exactly-once семантика

```python
async with conn.transaction():
    await conn.execute("INSERT INTO product_families...")
    await conn.execute("INSERT INTO outbox_events...")
```

### 2. Circuit Breaker
Защита от каскадных отказов при обращении к AI API:
- Порог отказов: 5
- Время восстановления: 60 секунд
- Fallback: возврат статуса `enrichment_failed`

### 3. Cache-Aside с Jitter
Redis кэширование с защитой от cache stampede:
- TTL = 600 + random(0, 120) секунд
- Формат ключей: `product:fam:{uuid}:full`
- Сериализация: msgpack

### 4. Raw Products Import Worker
Автоматический импорт товаров от Parser Service:
- Чтение из Kafka топика `raw-products`
- Дедупликация по `source_url`
- Транзакционное создание товара с атрибутами, документами и изображениями
- Автоматический запуск AI-обогащения через Outbox Pattern
- Статистика: imported/duplicates/errors

```python
# Проверка дубликата
existing = await repository.find_by_source_url(source_url)
if existing:
    return "duplicate"

# Создание товара с атрибутами и документами в одной транзакции
await repository.create_with_outbox(
    product=product,
    event=enrichment_event,
    attributes=raw_product["attributes"],
    documents=raw_product["documents"],
    images=raw_product["images"],
)
```

## 🛠️ Технологический стек

| Компонент | Технология |
|-----------|------------|
| Язык | Python 3.11+ |
| Web Framework | FastAPI |
| База данных | PostgreSQL (asyncpg) |
| Кэш | Redis (aioredis) |
| Очередь сообщений | Kafka (aiokafka) |
| AI/ML | Google Vertex AI (Gemini) |
| Контейнеризация | Docker |
| Оркестрация | Kubernetes (Helm) |

## 🚀 Быстрый старт

### Требования
- Python 3.11+
- Docker & Docker Compose
- Make

### Локальная разработка

```bash
# 1. Клонируйте репозиторий
git clone https://github.com/Zashita-LTD/Product_Service.git
cd Product_Service

# 2. Создайте виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows

# 3. Установите зависимости
make install

# 4. Скопируйте конфигурацию
cp .env.example .env
# Отредактируйте .env с вашими настройками

# 5. Поднимите инфраструктуру
make docker-up

# 6. Примените миграции
make migrate

# 7. Запустите API
make run-api

# 8. В другом терминале запустите воркер (опционально)
make run-worker
```

### Docker Compose

```bash
# Запуск всех сервисов
docker-compose -f deploy/docker/docker-compose.yml up -d

# Просмотр логов
docker-compose -f deploy/docker/docker-compose.yml logs -f

# Остановка
docker-compose -f deploy/docker/docker-compose.yml down
```

## 📡 API Endpoints

### Создание товарного семейства
```bash
curl -X POST http://localhost:8000/api/v1/products/families \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: unique-request-id" \
  -d '{
    "name_technical": "Кирпич М150",
    "category_id": 1
  }'
```

**Ответ:**
```json
{
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "name_technical": "Кирпич М150",
  "category_id": 1,
  "quality_score": null,
  "enrichment_status": "pending",
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00"
}
```

### Получение товарного семейства
```bash
curl http://localhost:8000/api/v1/products/families/{uuid}
```

### Запуск AI обогащения
```bash
curl -X POST http://localhost:8000/api/v1/products/families/{uuid}/enrich
```

**Ответ:**
```json
{
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "quality_score": 0.85,
  "enrichment_status": "enriched",
  "message": "Product enriched successfully"
}
```

### Health Check
```bash
curl http://localhost:8000/api/v1/products/health
```

### Семантический поиск (pgvector)
```bash
curl -X POST http://localhost:8000/api/v1/products/search/semantic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "кирпич керамический",
    "page": 1,
    "per_page": 20,
    "filters": {
      "category_id": 10
    }
  }'
```

**Ответ:**
```json
{
  "data": [
    {
      "uuid": "550e8400-e29b-41d4-a716-446655440000",
      "name_technical": "Кирпич М150",
      "category": { "id": 10, "name": "Кирпич", "path": ["Стройматериалы", "Кирпич"] },
      "similarity": 0.94
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total_items": 128,
    "total_pages": 7
  }
}
```

### Backfill эмбеддингов

После миграции 008 и настройки Vertex AI выполните бэкфилл для legacy-товаров:

```bash
python -m cmd.backfill_embeddings.main
```

Переменная `EMBEDDING_BATCH_SIZE` контролирует размер батча (по умолчанию 50).

## 🧪 Тестирование

```bash
# Все тесты
make test

# Только unit тесты
make test-unit

# Только интеграционные тесты
make test-int

# С покрытием
make coverage
```

## 📊 Мониторинг

### Метрики
- Prometheus метрики доступны на `/api/v1/products/metrics`
- Grafana дашборды в `deploy/grafana/dashboards/`
- Alertmanager для уведомлений об инцидентах

### Компоненты мониторинга

**Prometheus** (http://localhost:9090):
- Сбор метрик каждые 15 секунд
- Хранение time-series данных
- Evaluation alerting rules

**Grafana** (http://localhost:3000):
- Product Service Dashboard - HTTP, Kafka, AI enrichment, БД
- Parser Service Dashboard - Парсинг, прокси, anti-detection
- Login: admin/admin

**Alertmanager** (http://localhost:9093):
- High Error Rate (>5%)
- Enrichment Failures
- Kafka Consumer Lag
- Parser Blocked
- Low Parsing Rate

Подробная документация: [docs/monitoring.md](docs/monitoring.md)

### Логирование
- Структурированные JSON логи
- Поддержка Request-ID для трейсинга
- Уровни: DEBUG, INFO, WARNING, ERROR, CRITICAL

## 🔧 Конфигурация

Все настройки через переменные окружения (см. `.env.example`):

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `DATABASE_URL` | PostgreSQL connection string | - |
| `REDIS_URL` | Redis connection URL | redis://localhost:6379/0 |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka brokers | localhost:9092 |
| `KAFKA_RAW_PRODUCTS_TOPIC` | Топик для импорта товаров | raw-products |
| `DEFAULT_CATEGORY_ID` | ID категории по умолчанию | 1 |
| `VERTEX_PROJECT_ID` | Google Cloud project ID | - |
| `VERTEX_EMBEDDING_MODEL` | Vertex AI модель для эмбеддингов | text-embedding-004 |
| `EMBEDDING_BATCH_SIZE` | Размер батча для backfill скрипта | 50 |
| `LOG_LEVEL` | Уровень логирования | INFO |

## 📦 CI/CD

GitHub Actions workflow (`.github/workflows/ci.yml`):

1. **Lint** - Black, isort, Flake8, MyPy
2. **Test** - Unit и Integration тесты
3. **Build** - Multi-stage Docker образы
4. **Deploy** - Автодеплой в staging/production

## 🤝 Разработка

```bash
# Форматирование кода
make format

# Проверка линтерами
make lint

# Проверка типов
make typecheck
```

## 📄 Лицензия

Proprietary - Zashita LTD © 2024

## 📞 Контакты

- **Team**: dev@zashita.ltd
- **Issues**: [GitHub Issues](https://github.com/Zashita-LTD/Product_Service/issues)
