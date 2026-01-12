# Parser Service - Quick Start Guide

This guide will help you get the parser service up and running quickly.

## Prerequisites

- Docker and Docker Compose installed
- Network `product-service_backend` created (will be auto-created by main docker-compose)
- Kafka running on the `product-service_backend` network

## Option 1: Run with Main Infrastructure

1. **Start the main Product Service infrastructure** (includes Kafka, Postgres, Redis):
   ```bash
   cd /path/to/Product_Service
   docker-compose -f deploy/docker/docker-compose.yml up -d
   ```

2. **Start the parser service**:
   ```bash
   cd parser-service
   docker-compose up -d
   ```

3. **View logs**:
   ```bash
   docker-compose logs -f parser-service
   ```

## Option 2: Run Standalone (Development)

1. **Ensure you have Python 3.11+ and virtual environment**:
   ```bash
   cd parser-service
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

3. **Configure environment** (copy and edit):
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

4. **Run the parser**:
   ```bash
   python cmd/main.py
   ```

## Configuration

### Essential Settings

Edit `docker-compose.yml` or create `.env` file:

```bash
# Kafka connection (required)
KAFKA_BOOTSTRAP_SERVERS=kafka:29092

# Target website
PETROVICH_BASE_URL=https://moscow.petrovich.ru

# Parsing limits
MAX_PRODUCTS_PER_RUN=10000
PARSING_INTERVAL_SECONDS=21600  # 6 hours

# Browser settings
HEADLESS=true
```

### Optional: Proxy Configuration

To use proxies, create or edit `proxies.txt`:

```
# Format: http://user:pass@host:port
http://user:password@proxy1.example.com:8080
http://user:password@proxy2.example.com:8080
```

Or set via environment variable:
```bash
PROXY_LIST=http://user:pass@proxy1:8080,http://user:pass@proxy2:8080
```

## Testing

### Test Components
```bash
python test_components.py
```

### Test Docker Build
```bash
docker build -t parser-service:test .
```

### Manual Test Run (One-off)
```bash
# Set interval to 0 to run once
docker run --rm \
  -e KAFKA_BOOTSTRAP_SERVERS=kafka:29092 \
  -e PARSING_INTERVAL_SECONDS=0 \
  --network product-service_backend \
  parser-service:test
```

## Monitoring

### View Logs
```bash
# Follow logs
docker-compose logs -f parser-service

# Last 100 lines
docker-compose logs --tail=100 parser-service
```

### Check Kafka Messages

Use Kafka UI (included in main docker-compose):
1. Open http://localhost:8080
2. Navigate to Topics → `raw-products`
3. View messages

Or use CLI:
```bash
# Connect to kafka container
docker exec -it product-service-kafka kafka-console-consumer \
  --bootstrap-server localhost:29092 \
  --topic raw-products \
  --from-beginning
```

## Troubleshooting

### Parser not finding products
- Check if website structure changed
- Verify network connectivity
- Check logs for selector errors

### Kafka connection failed
```bash
# Verify Kafka is running
docker ps | grep kafka

# Check network
docker network inspect product-service_backend

# Test connection from parser container
docker exec -it parser-service nc -zv kafka 29092
```

### Out of memory
```bash
# Reduce concurrent pages in docker-compose.yml
MAX_CONCURRENT_PAGES=1

# Or increase container memory limit
deploy:
  resources:
    limits:
      memory: 8G
```

### SSL/Certificate errors
These are handled automatically in the Dockerfile with `NODE_TLS_REJECT_UNAUTHORIZED=0`.
If you still encounter issues, check your network's SSL inspection/proxy.

## Stopping the Service

```bash
# Stop parser service
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

## Production Deployment

For production use:

1. **Use real proxies** - Add to `proxies.txt`
2. **Adjust rate limits** - Increase delays to avoid detection
3. **Monitor performance** - Track CPU/Memory usage
4. **Set up alerts** - Monitor Kafka lag and parsing errors
5. **Scale horizontally** - Run multiple instances with different category filters

## Next Steps

- Review the [Full README](README.md) for detailed documentation
- Customize parser selectors if website structure changes
- Add more parsers for different websites (see `internal/parsers/`)
- Set up monitoring and alerting

## Support

For issues:
- Check logs: `docker-compose logs -f parser-service`
- Review README.md for detailed documentation
- Check GitHub Issues
- Contact: dev@zashita.ltd
