# Мониторинг Product Service

Система мониторинга Product Service построена на основе Prometheus и Grafana, обеспечивая полную наблюдаемость за производительностью, здоровьем и ошибками сервисов.

## Архитектура

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────┐
│  Product Service│────▶│  Prometheus  │────▶│   Grafana    │
│  Parser Service │     │   (Метрики)  │     │ (Дашборды)   │
└─────────────────┘     └──────────────┘     └──────────────┘
                              │
                              ▼
                        ┌──────────────┐
                        │ Alertmanager │
                        │   (Алерты)   │
                        └──────────────┘
```

## Компоненты

### 1. Prometheus

**Адрес:** http://localhost:9090

Prometheus собирает метрики со всех сервисов через HTTP эндпоинт `/metrics`:

- **Product Service API**: `http://api:8000/api/v1/products/metrics`
- **Enrichment Worker**: `http://worker-enrichment:8001/metrics` (planned)
- **Raw Products Worker**: `http://worker-raw-products:8002/metrics` (planned)
- **Parser Service**: `http://parser:8003/metrics` (planned)

**Конфигурация:** `deploy/prometheus/prometheus.yml`

**Интервал сбора:** 15 секунд

### 2. Grafana

**Адрес:** http://localhost:3000

**Логин:** admin / admin

Grafana предоставляет визуализацию метрик через дашборды:

- **Product Service Dashboard** - мониторинг Product Service
- **Parser Service Dashboard** - мониторинг Parser Service

**Конфигурация:**
- Datasource: `deploy/grafana/provisioning/datasources/prometheus.yml`
- Dashboard provisioning: `deploy/grafana/provisioning/dashboards/default.yml`
- Дашборды: `deploy/grafana/dashboards/`

### 3. Alertmanager

**Адрес:** http://localhost:9093

Alertmanager обрабатывает алерты от Prometheus и отправляет уведомления.

**Конфигурация:** `deploy/alertmanager/alertmanager.yml`

## Метрики

### Product Service

#### HTTP API Метрики

- **`http_requests_total`** - Общее количество HTTP запросов
  - Labels: `method`, `endpoint`, `status_code`
  
- **`http_request_duration_seconds`** - Длительность HTTP запросов (histogram)
  - Labels: `method`, `endpoint`
  - Buckets: 0.01s, 0.05s, 0.1s, 0.25s, 0.5s, 1s, 2.5s, 5s, 10s

#### Метрики продуктов

- **`products_total`** - Общее количество продуктов в БД
  
- **`products_by_enrichment_status`** - Продукты по статусу обогащения
  - Labels: `status` (pending, enriched, failed)
  
- **`products_by_source`** - Продукты по источнику
  - Labels: `source_name` (petrovich, leroymerlin, sdvor, obi)

#### Kafka Метрики

- **`kafka_messages_consumed_total`** - Потребленные Kafka сообщения
  - Labels: `topic`, `status` (success, error, duplicate)
  
- **`kafka_consumer_lag`** - Задержка Kafka consumer
  - Labels: `topic`, `partition`

#### AI Enrichment Метрики

- **`enrichment_requests_total`** - Запросы AI обогащения
  - Labels: `status` (success, error, timeout)
  
- **`enrichment_duration_seconds`** - Длительность AI обогащения (histogram)
  - Buckets: 0.5s, 1s, 2s, 5s, 10s, 30s, 60s

#### Database Метрики

- **`db_connections_active`** - Активные соединения с БД
  
- **`db_query_duration_seconds`** - Длительность DB запросов (histogram)
  - Labels: `operation` (select, insert, update)
  - Buckets: 0.001s, 0.005s, 0.01s, 0.05s, 0.1s, 0.5s, 1s

### Parser Service

#### Parsing Метрики

- **`parser_pages_parsed_total`** - Спарсенные страницы
  - Labels: `parser_name`, `page_type` (category, product)
  
- **`parser_products_extracted_total`** - Извлеченные продукты
  - Labels: `parser_name`, `status` (success, error)
  
- **`parser_parse_duration_seconds`** - Длительность парсинга (histogram)
  - Labels: `parser_name`, `page_type`
  - Buckets: 0.5s, 1s, 2s, 5s, 10s, 30s

#### Proxy Метрики

- **`parser_proxy_requests_total`** - Прокси запросы
  - Labels: `status` (success, failed, timeout)
  
- **`parser_proxy_pool_size`** - Размер пула прокси
  - Labels: `status` (good, bad)

#### Anti-Detection Метрики

- **`parser_blocked_requests_total`** - Заблокированные запросы
  - Labels: `parser_name`, `status_code` (403, 429, 503)
  
- **`parser_context_rotations_total`** - Ротации browser context
  - Labels: `parser_name`, `reason` (blocked, timeout, scheduled)

#### Kafka Producer Метрики

- **`parser_kafka_messages_produced_total`** - Отправленные Kafka сообщения
  - Labels: `status` (success, error)

## Алерты

### Product Service Alerts

#### HighErrorRate
- **Condition:** Error rate > 5% за 5 минут
- **Severity:** Critical
- **Description:** Высокий уровень ошибок 5xx в API

#### EnrichmentFailures
- **Condition:** > 0.1 ошибок обогащения в секунду за 15 минут
- **Severity:** Warning
- **Description:** Частые сбои AI обогащения

#### KafkaConsumerLag
- **Condition:** Consumer lag > 1000 сообщений за 15 минут
- **Severity:** Warning
- **Description:** Большая задержка Kafka consumer

### Parser Service Alerts

#### ParserBlocked
- **Condition:** > 0.5 блокировок в секунду за 5 минут
- **Severity:** Critical
- **Description:** Парсер блокируется anti-bot системой

#### ProxyPoolDepleted
- **Condition:** < 2 рабочих прокси за 5 минут
- **Severity:** Warning
- **Description:** Пул прокси почти исчерпан

#### LowParsingRate
- **Condition:** < 1 продукта в секунду за 30 минут
- **Severity:** Warning
- **Description:** Очень низкая скорость парсинга

## Запуск мониторинга

### Docker Compose

```bash
# Запуск всех сервисов включая мониторинг
cd deploy/docker
docker-compose up -d

# Проверка статуса
docker-compose ps

# Просмотр логов
docker-compose logs -f prometheus
docker-compose logs -f grafana
```

### Доступ к интерфейсам

1. **Prometheus UI:** http://localhost:9090
   - Targets: http://localhost:9090/targets
   - Alerts: http://localhost:9090/alerts
   - Graph: http://localhost:9090/graph

2. **Grafana:** http://localhost:3000
   - Логин: `admin`
   - Пароль: `admin`
   - Дашборды: Dashboards → Browse

3. **Alertmanager:** http://localhost:9093
   - Alerts: http://localhost:9093/#/alerts

## Примеры запросов

### Prometheus Queries

#### HTTP Metrics
```promql
# RPS по эндпоинтам
rate(http_requests_total[5m])

# Error rate
rate(http_requests_total{status_code=~"5.."}[5m]) / rate(http_requests_total[5m])

# Latency P95
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

#### Kafka Metrics
```promql
# Messages per second
rate(kafka_messages_consumed_total[5m])

# Consumer lag
kafka_consumer_lag

# Success rate
rate(kafka_messages_consumed_total{status="success"}[5m]) / rate(kafka_messages_consumed_total[5m])
```

#### Enrichment Metrics
```promql
# Enrichment RPS
rate(enrichment_requests_total[5m])

# Success rate
rate(enrichment_requests_total{status="success"}[5m]) / rate(enrichment_requests_total[5m])

# Duration P99
histogram_quantile(0.99, rate(enrichment_duration_seconds_bucket[5m]))
```

#### Parser Metrics
```promql
# Products per minute
rate(parser_products_extracted_total{status="success"}[1m]) * 60

# Success rate by parser
rate(parser_products_extracted_total{status="success"}[5m]) / rate(parser_products_extracted_total[5m])

# Blocked requests
rate(parser_blocked_requests_total[5m])
```

## Best Practices

### Security

**Метрики эндпоинт:**
- В production окружении рекомендуется ограничить доступ к `/metrics` эндпоинту
- Используйте network policies для доступа только из Prometheus
- Рассмотрите добавление базовой аутентификации или IP whitelist
- Пример nginx конфигурации для ограничения доступа:

```nginx
location /api/v1/products/metrics {
    allow 10.0.0.0/8;  # Internal network
    deny all;
    proxy_pass http://product-service;
}
```

### Мониторинг

1. **Используйте правильные интервалы:**
   - Scrape interval: 15-30 секунд для большинства метрик
   - Evaluation interval: 15-30 секунд для правил алертинга
   - Retention: минимум 15 дней для трендов

2. **Оптимизируйте метрики:**
   - Избегайте high-cardinality labels (user IDs, timestamps)
   - Ограничьте количество уникальных label values
   - Используйте recording rules для сложных запросов

3. **Настройте алерты правильно:**
   - Добавьте `for:` duration для избежания ложных срабатываний
   - Используйте severity levels (critical, warning, info)
   - Включайте контекст в annotations

## Полезные ссылки

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [PromQL Guide](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Alertmanager Documentation](https://prometheus.io/docs/alerting/latest/alertmanager/)
