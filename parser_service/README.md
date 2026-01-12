# Parser Service

Scraping service for construction materials stores. Extracts product data and publishes to Kafka for processing by Product Service.

## Supported Stores

- **Petrovich** (petrovich.ru) - Traditional HTML scraping
- **Leroy Merlin** (leroymerlin.ru) - Next.js with __NEXT_DATA__ extraction
- **Строительный Двор** (sdvor.com) - Classic HTML parsing
- **OBI** (obi.ru) - React SPA with dynamic content

## Architecture

```
parser_service/
├── cmd/
│   └── main.py              # Entry point with ParserScheduler
├── internal/
│   ├── models/
│   │   └── product.py       # RawProduct data model
│   └── parsers/
│       ├── base.py          # BaseParser abstract class
│       ├── petrovich.py     # Petrovich parser
│       ├── leroymerlin.py   # Leroy Merlin parser
│       ├── sdvor.py         # Sdvor parser
│       └── obi.py           # OBI parser
└── config/
    └── settings.py          # Configuration management
```

## Features

### Multi-Store Support
Enable/disable parsers via `ENABLED_PARSERS` environment variable:
```bash
ENABLED_PARSERS=petrovich,leroymerlin,sdvor,obi
```

### Intelligent Data Extraction
Each parser implements a 3-tier extraction strategy:
1. **JSON-LD (Schema.org)** - Structured data if available
2. **__NEXT_DATA__** - Next.js server-side data (Leroy Merlin)
3. **HTML Parsing** - Fallback DOM parsing

### Product Data Model
`RawProduct` includes:
- Source URL and store name
- Product name, brand, category breadcrumbs
- Attributes/specifications
- Images and documents (PDFs, certificates)
- Price and availability
- Structured data (JSON-LD, __NEXT_DATA__)

### Kafka Integration
Publishes scraped products to `raw-products` Kafka topic for ingestion by Product Service.

## Configuration

### Environment Variables

```bash
# Parser Configuration
ENABLED_PARSERS=petrovich,leroymerlin,sdvor,obi

# Store URLs
PETROVICH_BASE_URL=https://petrovich.ru
LEROYMERLIN_BASE_URL=https://leroymerlin.ru
SDVOR_BASE_URL=https://sdvor.com
OBI_BASE_URL=https://obi.ru

# Scraping Settings
HEADLESS_BROWSER=true
MAX_CONCURRENT_REQUESTS=5
REQUEST_TIMEOUT=30000
REQUESTS_PER_SECOND=2
MAX_RETRIES=3
RETRY_DELAY=5

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_RAW_PRODUCTS_TOPIC=raw-products
```

## Usage

### Prerequisites

1. Install dependencies:
```bash
pip install -r requirements.txt
playwright install chromium
```

2. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Ensure Kafka is running:
```bash
# Start Kafka (if using Docker Compose)
make docker-up
```

### Running the Parser Service

```bash
# Run all enabled parsers
make run-parser

# Or run directly
cd parser_service/cmd
python main.py
```

### Selective Parser Execution

To run specific parsers only:
```bash
ENABLED_PARSERS=leroymerlin,sdvor make run-parser
```

## Parser Implementation Details

### Leroy Merlin (leroymerlin.ru)
- **Technology**: Next.js SSR
- **Primary Data Source**: `__NEXT_DATA__` script tag
- **Fallback**: JSON-LD, HTML parsing
- **Pagination**: `?page=N`
- **Special Features**: Document section for certificates and manuals

### Строительный Двор (sdvor.com)
- **Technology**: Classic HTML
- **Data Source**: HTML elements, tables
- **Attributes**: `<table class="properties">` or `<dl>`
- **Documents**: PDF links in product card
- **Fast**: No JavaScript rendering needed

### OBI (obi.ru)
- **Technology**: React SPA
- **Data Source**: Dynamically loaded content
- **Requirement**: Wait for React component rendering
- **Selectors**: `.product-card`, `[data-testid="product-*"]`
- **Attributes**: Tab-based loading (click "Характеристики")

### Petrovich (petrovich.ru)
- **Technology**: Traditional HTML
- **Data Source**: Microdata, JSON-LD
- **Attributes**: Itemprop attributes, breadcrumbs
- **Gallery**: Multiple product images

## Data Flow

```
┌─────────────────┐
│ Parser Service  │
│                 │
│ ┌─────────────┐ │
│ │  Scheduler  │ │
│ └──────┬──────┘ │
│        │        │
│   ┌────▼────┐   │
│   │ Parsers │   │
│   └────┬────┘   │
└────────┼────────┘
         │
    Raw Products
         │
         ▼
   ┌──────────┐
   │  Kafka   │
   │  Topic   │
   └─────┬────┘
         │
         ▼
┌────────────────────┐
│  Product Service   │
│  (Ingestion)       │
└────────────────────┘
```

## Rate Limiting

Default: 2 requests per second per parser to avoid overwhelming target sites.

Configure via:
```bash
REQUESTS_PER_SECOND=2
```

## Error Handling

- Automatic retries on failure (configurable)
- Graceful degradation (JSON-LD → __NEXT_DATA__ → HTML)
- Detailed logging of scraping errors
- Continues with next product on individual failures

## Logging

Logs include:
- Parser name and operation
- URLs being scraped
- Success/failure status
- Product counts per category
- Errors with stack traces

## Development

### Adding a New Parser

1. Create new parser class in `parser_service/internal/parsers/`:

```python
from parser_service.internal.parsers.base import BaseParser
from parser_service.internal.models.product import RawProduct

class MyStoreParser(BaseParser):
    @property
    def name(self) -> str:
        return "mystore.com"
    
    async def get_category_urls(self, page: Page) -> List[str]:
        # Implementation
        pass
    
    async def get_product_urls(self, page: Page, category_url: str) -> AsyncGenerator[str, None]:
        # Implementation
        pass
    
    async def parse_product(self, page: Page, url: str) -> Optional[RawProduct]:
        # Implementation
        pass
```

2. Add to `parser_service/internal/parsers/__init__.py`:
```python
from parser_service.internal.parsers.mystore import MyStoreParser

__all__ = [..., "MyStoreParser"]
```

3. Update `parser_service/cmd/main.py`:
```python
parser_map = {
    ...
    "mystore": lambda: MyStoreParser(settings.MYSTORE_BASE_URL),
}
```

4. Add configuration in `parser_service/config/settings.py`:
```python
MYSTORE_BASE_URL: str = os.getenv("MYSTORE_BASE_URL", "https://mystore.com")
```

### Testing

```bash
# Test imports
python -c "from parser_service.internal.parsers import *; print('✓ All parsers loaded')"

# Test configuration
python -c "from parser_service.config import settings; print(settings.get_enabled_parsers())"

# Test RawProduct model
python -c "from parser_service.internal.models import RawProduct; print(RawProduct().to_dict())"
```

## Troubleshooting

### Browser not installed
```bash
playwright install chromium
```

### Kafka connection errors
Check `KAFKA_BOOTSTRAP_SERVERS` and ensure Kafka is running:
```bash
docker-compose -f deploy/docker/docker-compose.yml up -d kafka
```

### Import errors
Ensure you're running from repository root:
```bash
cd /path/to/Product_Service
python parser_service/cmd/main.py
```

### Rate limiting / 429 errors
Reduce `REQUESTS_PER_SECOND`:
```bash
REQUESTS_PER_SECOND=1 make run-parser
```

## License

Proprietary - Zashita LTD © 2024
