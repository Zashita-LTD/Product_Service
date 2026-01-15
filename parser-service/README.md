# Parser Service 🕷️

**Smart Web Scraper** for creating Digital Twins from moscow.petrovich.ru

## Overview

Parser Service is a microservice that extracts structured product data from moscow.petrovich.ru and publishes it to Kafka for processing by the Product Service. It's designed to support Web 3.0 Agent-to-Agent economy by creating AI-readable product representations.

## Features

✅ **Multi-Source Data Extraction**
- JSON-LD (Schema.org) - highest priority
- __NEXT_DATA__ (Next.js SSR) - secondary source  
- HTML parsing - fallback method

✅ **Anti-Detection**
- Playwright headless browser with stealth scripts
- User-Agent rotation
- Random delays between requests (1-4 seconds)
- Proxy pool with health tracking

✅ **Proxy Pool**
- Automatic proxy rotation on errors (403, 429, timeout)
- Bad proxy tracking and auto-reset
- Support for authenticated proxies

✅ **Kafka Integration**
- Publishes to `raw-products` topic
- Gzip compression for bandwidth efficiency
- Uses source_url as partition key for consistency
- Exactly-once delivery semantics

✅ **Production Ready**
- Graceful shutdown (SIGTERM/SIGINT)
- Structured JSON logging
- Configurable limits and intervals
- Docker containerization

## Architecture

```
parser-service/
├── cmd/
│   └── main.py                 # Entry point with scheduler
├── internal/
│   ├── browser/
│   │   └── instance.py         # Playwright + Proxy Pool
│   ├── parsers/
│   │   ├── base.py             # Abstract parser
│   │   └── petrovich.py        # Petrovich implementation
│   ├── kafka/
│   │   └── producer.py         # Kafka producer
│   └── models/
│       └── product.py          # Pydantic models
├── config/
│   └── settings.py             # Configuration
├── pkg/
│   └── logger/
│       └── logger.py           # Structured logging
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── proxies.txt
└── README.md
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Kafka running on `kafka:29092` (or configure via env vars)
- Network `product-service_backend` created

### Running with Docker Compose

```bash
# 1. Navigate to parser-service directory
cd parser-service

# 2. (Optional) Configure proxies
# Edit proxies.txt with your proxy list

# 3. Build and run
docker-compose up -d

# 4. View logs
docker-compose logs -f parser-service

# 5. Stop
docker-compose down
```

### Running Standalone

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Install Playwright browsers
playwright install chromium

# 3. Set environment variables
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export PETROVICH_BASE_URL=https://moscow.petrovich.ru
export HEADLESS=true

# 4. Run parser
python cmd/main.py
```

## Configuration

All configuration is done via environment variables:

### Kafka Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker addresses | `kafka:29092` |
| `KAFKA_RAW_PRODUCTS_TOPIC` | Topic for raw products | `raw-products` |
| `KAFKA_CLIENT_ID` | Client identifier | `parser-service` |
| `KAFKA_COMPRESSION_TYPE` | Message compression | `gzip` |

### Parsing Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `PETROVICH_BASE_URL` | Base URL to parse | `https://moscow.petrovich.ru` |
| `PARSING_INTERVAL_SECONDS` | Interval between runs | `21600` (6 hours) |
| `HEADLESS` | Run browser headless | `true` |
| `MAX_CONCURRENT_PAGES` | Max parallel pages | `3` |
| `MIN_DELAY_SECONDS` | Min delay between requests | `1.5` |
| `MAX_DELAY_SECONDS` | Max delay between requests | `4.0` |
| `MAX_RETRIES` | Max retry attempts | `3` |
| `MAX_PRODUCTS_PER_RUN` | Max products per run | `10000` |

### Proxy Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `PROXY_LIST` | Comma-separated proxy URLs | `None` |
| `PROXY_FILE` | Path to proxy file | `proxies.txt` |

Proxy format: `http://user:pass@host:port` or `http://host:port`

### Logging Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Log level | `INFO` |
| `LOG_FORMAT` | Format (json or text) | `json` |

## Data Model

The parser extracts comprehensive product information:

```python
{
    "id": "uuid",
    "source_url": "https://...",
    "source_name": "moscow.petrovich.ru",
    "external_id": "...",
    "sku": "...",
    
    # Core info
    "name_original": "Product Name",
    "name_technical": "...",
    "brand": "Brand Name",
    "manufacturer": "...",
    
    # Classification
    "category_path": ["Level1", "Level2", "Level3"],
    "category_id": "...",
    
    # Description
    "description_short": "...",
    "description_full": "...",
    
    # Attributes (KEY for AI)
    "attributes": [
        {"name": "Weight", "value": "5", "type": "unit", "unit": "kg"},
        {"name": "Material", "value": "Steel", "type": "text"}
    ],
    
    # Pricing
    "price": {
        "current": 1999.99,
        "currency": "RUB",
        "original": 2499.99,
        "discount_percent": 20.0
    },
    
    # Availability
    "availability": {
        "status": "in_stock",
        "quantity": 15,
        "store_name": "Moscow"
    },
    
    # Media
    "images": [
        {"url": "https://...", "alt": "...", "position": 0}
    ],
    
    # Documents (CRITICAL for AI agents)
    "documents": [
        {
            "url": "https://...manual.pdf",
            "title": "User Manual",
            "type": "manual",
            "file_format": "pdf"
        },
        {
            "url": "https://...certificate.pdf",
            "title": "Quality Certificate",
            "type": "certificate",
            "file_format": "pdf"
        }
    ],
    
    # Schema.org data (raw JSON-LD)
    "schema_org_data": {...},
    
    # Metadata
    "parsed_at": "2024-01-15T10:30:00Z",
    "parser_version": "1.0.0"
}
```

## Extraction Strategy

The parser uses a **priority-based extraction strategy**:

### 1. JSON-LD (Schema.org) - Priority 1
- Cleanest and most structured data
- Standardized Schema.org Product format
- Best for AI consumption

### 2. __NEXT_DATA__ - Priority 2
- Next.js server-side rendered data
- Usually contains full product details
- Requires navigation through nested structure

### 3. HTML Parsing - Priority 3
- Fallback when structured data unavailable
- Uses BeautifulSoup with CSS selectors
- Less reliable but ensures data extraction

## Proxy Pool

The proxy pool automatically manages proxy health:

1. **Initialization**: Load proxies from `PROXY_LIST` env var or `proxies.txt` file
2. **Random Selection**: Choose random proxy for each browser context
3. **Error Detection**: Monitor for timeouts, 403, 429 errors
4. **Bad Proxy Marking**: Automatically mark failed proxies as bad
5. **Auto Reset**: Reset pool when all proxies are marked bad
6. **Context Rotation**: Create new browser context with fresh proxy

## Integration with Product Service

1. Parser extracts product data and creates `RawProduct` model
2. Product is serialized to JSON with gzip compression
3. Message is sent to Kafka topic `raw-products`
4. Partition key is `source_url` for consistent routing
5. Product Service consumer processes the message
6. AI enrichment is triggered for the new product

## Monitoring

### Logs

Structured JSON logs include:

```json
{
    "timestamp": "2024-01-15T10:30:00Z",
    "level": "INFO",
    "logger": "internal.parsers.petrovich",
    "message": "Product parsed successfully",
    "url": "https://...",
    "name": "Product Name",
    "attributes_count": 15,
    "documents_count": 3
}
```

### Metrics

Key metrics logged:
- Products parsed per run
- Kafka messages sent
- Proxy pool health
- Errors and retries

## Development

### Running Tests

```bash
# TODO: Add tests
pytest tests/
```

### Code Quality

```bash
# Format code
black .
isort .

# Lint
flake8 .

# Type check
mypy .
```

## Deployment

### Kubernetes (Helm)

```yaml
# TODO: Add Helm chart
```

### Scaling Considerations

- **Vertical Scaling**: Increase memory/CPU for more concurrent pages
- **Horizontal Scaling**: Run multiple instances with different category subsets
- **Proxy Scaling**: Add more proxies to avoid rate limiting
- **Kafka Partitions**: Increase partitions for higher throughput

## Troubleshooting

### No products found

1. Check if website structure changed (update selectors)
2. Verify network connectivity
3. Check if being blocked (403/429 errors)

### Proxy errors

1. Verify proxy credentials and format
2. Test proxies manually
3. Check proxy pool logs for health status

### Kafka connection issues

1. Verify `KAFKA_BOOTSTRAP_SERVERS` is correct
2. Check network connectivity to Kafka
3. Ensure topic `raw-products` exists

### Out of memory

1. Reduce `MAX_CONCURRENT_PAGES`
2. Increase container memory limit
3. Enable page cleanup (close pages after use)

## Roadmap

- [ ] Add more source websites (Leroy Merlin, OBI, etc.)
- [ ] Implement incremental parsing (only new products)
- [ ] Add product deduplication
- [ ] Implement distributed parsing (multiple workers)
- [ ] Add metrics export (Prometheus)
- [ ] Add health check endpoint
- [ ] Implement smart retry with exponential backoff
- [ ] Add captcha solving

## License

Proprietary - Zashita LTD © 2024

## Support

For issues and questions:
- GitHub Issues: [Product_Service/issues](https://github.com/Zashita-LTD/Product_Service/issues)
- Email: dev@zashita.ltd
