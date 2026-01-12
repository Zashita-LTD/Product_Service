"""
Prometheus Metrics for Product Service.

Defines all metrics for monitoring Product Service performance and health.
"""

from prometheus_client import Counter, Histogram, Gauge

# Метрики API
HTTP_REQUESTS_TOTAL = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

HTTP_REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Метрики продуктов
PRODUCTS_TOTAL = Gauge(
    'products_total',
    'Total number of products in database'
)

PRODUCTS_BY_STATUS = Gauge(
    'products_by_enrichment_status',
    'Products by enrichment status',
    ['status']
)

PRODUCTS_BY_SOURCE = Gauge(
    'products_by_source',
    'Products by source',
    ['source_name']
)

# Метрики Kafka
KAFKA_MESSAGES_CONSUMED = Counter(
    'kafka_messages_consumed_total',
    'Total Kafka messages consumed',
    ['topic', 'status']  # status: success, error, duplicate
)

KAFKA_CONSUMER_LAG = Gauge(
    'kafka_consumer_lag',
    'Kafka consumer lag',
    ['topic', 'partition']
)

# Метрики AI обогащения
ENRICHMENT_REQUESTS = Counter(
    'enrichment_requests_total',
    'Total AI enrichment requests',
    ['status']  # success, error, timeout
)

ENRICHMENT_DURATION = Histogram(
    'enrichment_duration_seconds',
    'AI enrichment duration',
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

# Метрики БД
DB_CONNECTIONS_ACTIVE = Gauge(
    'db_connections_active',
    'Active database connections'
)

DB_QUERY_DURATION = Histogram(
    'db_query_duration_seconds',
    'Database query duration',
    ['operation'],  # select, insert, update
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
)
