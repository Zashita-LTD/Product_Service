"""
Prometheus Metrics for Parser Service.

Defines all metrics for monitoring Parser Service performance and health.
"""

from prometheus_client import Counter, Histogram, Gauge

# Метрики парсинга
PAGES_PARSED = Counter(
    'parser_pages_parsed_total',
    'Total pages parsed',
    ['parser_name', 'page_type']  # page_type: category, product
)

PRODUCTS_EXTRACTED = Counter(
    'parser_products_extracted_total',
    'Total products extracted',
    ['parser_name', 'status']  # status: success, error
)

PARSE_DURATION = Histogram(
    'parser_parse_duration_seconds',
    'Page parsing duration',
    ['parser_name', 'page_type'],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

# Метрики прокси
PROXY_REQUESTS = Counter(
    'parser_proxy_requests_total',
    'Proxy requests',
    ['status']  # success, failed, timeout
)

PROXY_POOL_SIZE = Gauge(
    'parser_proxy_pool_size',
    'Proxy pool size',
    ['status']  # good, bad
)

# Метрики Anti-Detection
BLOCKED_REQUESTS = Counter(
    'parser_blocked_requests_total',
    'Requests blocked by anti-bot',
    ['parser_name', 'status_code']  # 403, 429, 503
)

CONTEXT_ROTATIONS = Counter(
    'parser_context_rotations_total',
    'Browser context rotations',
    ['parser_name', 'reason']  # blocked, timeout, scheduled
)

# Метрики Kafka Producer
KAFKA_MESSAGES_PRODUCED = Counter(
    'parser_kafka_messages_produced_total',
    'Kafka messages produced',
    ['status']  # success, error
)
