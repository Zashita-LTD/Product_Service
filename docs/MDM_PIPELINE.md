# MDM Pipeline - Master Data Management

## Обзор

Product Service теперь включает интеллектуальный MDM пайплайн для обработки данных от парсеров.

**Главный принцип: Ни байта данных не теряем!**

## Архитектура

```
┌──────────────────┐     ┌───────────────────┐     ┌──────────────────┐
│   Parser Service │────▶│   Kafka Topic     │────▶│  Worker Raw      │
│   (scrapers)     │     │  raw-products     │     │  Products        │
└──────────────────┘     └───────────────────┘     └────────┬─────────┘
                                                            │
                                                            ▼
                                                  ┌──────────────────┐
                                                  │ ProductRefinery  │
                                                  │  (MDM Pipeline)  │
                                                  └────────┬─────────┘
                                                           │
                    ┌──────────────────┬──────────────────┬┴──────────────────┐
                    ▼                  ▼                  ▼                   ▼
           ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐
           │ Save Snapshot │  │ Deduplication │  │  Data Merger  │  │ Manufacturer  │
           │ (raw_data)    │  │  Strategies   │  │ (enrichment)  │  │    Linker     │
           └───────────────┘  └───────────────┘  └───────────────┘  └───────────────┘
```

## Включение/Выключение

```bash
# Включить MDM Pipeline (по умолчанию)
USE_MDM_PIPELINE=true

# Использовать старую логику (прямой импорт)
USE_MDM_PIPELINE=false
```

## Компоненты

### 1. Raw Product Snapshots

Таблица `raw_product_snapshots` хранит **все** данные от парсеров:

```sql
CREATE TABLE raw_product_snapshots (
    id UUID PRIMARY KEY,
    source_name VARCHAR(50),      -- 'petrovich', 'leroy'
    source_url VARCHAR(500),      -- Полный URL
    external_id VARCHAR(100),     -- ID на сайте
    raw_data JSONB,               -- ВЕСЬ JSON от парсера
    content_hash VARCHAR(64),     -- SHA256 для дедупликации
    extracted_ean VARCHAR(20),    -- Штрих-код
    extracted_sku VARCHAR(50),    -- Артикул
    extracted_brand VARCHAR(100), -- Бренд
    processed BOOLEAN,
    processing_result VARCHAR(50),
    linked_product_uuid UUID,
    created_at TIMESTAMP
);
```

### 2. Стратегии Дедупликации

Порядок поиска дубликатов (от точного к fuzzy):

| # | Стратегия | Уверенность | Описание |
|---|-----------|-------------|----------|
| 1 | URL Match | 100% | Точное совпадение source_url (обновление) |
| 2 | EAN Match | 99% | По штрих-коду (EAN-13/EAN-8) |
| 3 | SKU+Brand | 95% | Артикул + производитель |
| 4 | Vector Search | 92%+ | Семантический поиск (pgvector) |
| 5 | Name Match | 85% | По нормализованному названию |

```python
# Пороги
EAN_CONFIDENCE = 0.99
SKU_BRAND_CONFIDENCE = 0.95
VECTOR_THRESHOLD = 0.92
NAME_THRESHOLD = 0.85
```

### 3. Data Merger

Логика слияния данных из разных источников:

```python
class DataMerger:
    # Приоритет источников
    SOURCE_PRIORITY = {
        'knauf': 10,      # Официальный сайт
        'bosch': 10,
        'petrovich': 50,  # Крупный ритейл
        'leroy': 50,
        'unknown': 100,
    }
```

**Правила слияния:**

| Данные | Правило |
|--------|---------|
| Название | Сохраняем первое "чистое" |
| Описание | Берём самое длинное (если новое > старое * 1.5) |
| Изображения | Объединяем из всех источников |
| Атрибуты | Добавляем недостающие |
| Документы | Объединяем (PDF, инструкции) |

### 4. Product Source Links

Связь товара с несколькими источниками:

```sql
CREATE TABLE product_source_links (
    product_uuid UUID,
    source_name VARCHAR(50),
    source_url VARCHAR(500),
    priority INTEGER,
    contributes_name BOOLEAN,
    contributes_images BOOLEAN,
    -- ...
);
```

### 5. Enrichment Audit Log

Логируем каждое действие для отладки:

```sql
CREATE TABLE enrichment_audit_log (
    action VARCHAR(50),         -- 'created', 'merged', 'enriched_images'
    action_details JSONB,
    ai_model VARCHAR(50),
    ai_confidence DECIMAL(5,4)
);
```

## Пример работы

### Сценарий: Один товар из трёх магазинов

**1. Петрович отдаёт первый снимок:**
```json
{
  "source_url": "https://petrovich.ru/rotband",
  "name_original": "Штукатурка Ротбанд 30 кг",
  "brand": "Knauf",
  "ean": "4607026710047",
  "images": ["img1.jpg"]
}
```

→ Создаётся новый ProductFamily
→ Привязывается к Manufacturer "Knauf"

**2. Леруа Мерлен отдаёт тот же товар:**
```json
{
  "source_url": "https://leroymerlin.ru/product/456",
  "name_original": "Ротбанд Кнауф штукатурка гипсовая",
  "ean": "4607026710047",
  "images": ["img2.jpg", "img3.jpg"],
  "attributes": [{"name": "Срок годности", "value": "6 мес"}]
}
```

→ Дедупликация по EAN → найден существующий товар
→ Merge: добавлены 2 фото и 1 атрибут
→ Создана связь product_source_links

**3. ВсеИнструменты отдаёт документы:**
```json
{
  "source_url": "https://vseinstrumenti.ru/rot30",
  "name_original": "Knauf Ротбанд",
  "sku": "ROT-30",
  "brand": "Knauf", 
  "documents": [{"url": "manual.pdf", "title": "Инструкция"}]
}
```

→ Дедупликация по SKU+Brand → найден тот же товар
→ Merge: добавлен документ

**Результат: Мега-карточка**
- 3 фото из разных источников
- Полный набор атрибутов
- Документация
- Связь с производителем Knauf

## API Изменения

### Статусы обработки

```python
# Новые статусы в Kafka метриках
KAFKA_MESSAGES_CONSUMED.labels(status='enriched')  # MDM: обогащён
KAFKA_MESSAGES_CONSUMED.labels(status='success')   # Создан
KAFKA_MESSAGES_CONSUMED.labels(status='duplicate') # Дубль
KAFKA_MESSAGES_CONSUMED.labels(status='error')     # Ошибка
```

### Новые эндпоинты (TODO)

```
GET /api/v1/products/{uuid}/sources     # Все источники товара
GET /api/v1/products/{uuid}/audit       # История обогащения
GET /api/v1/snapshots/{source_url}      # Сырой снимок по URL
```

## Миграция

```bash
# Применить миграцию
cd product-service
python -m cmd.migrator.main

# Или через Makefile
make migrate
```

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| USE_MDM_PIPELINE | Включить MDM логику | true |
| VERTEX_PROJECT_ID | Google Cloud проект для AI | - |
| VERTEX_EMBEDDING_MODEL | Модель эмбеддингов | text-embedding-004 |
| DEFAULT_CATEGORY_ID | Категория по умолчанию | 1 |

## Мониторинг

### Grafana Dashboard

```promql
# Скорость обработки
rate(kafka_messages_consumed_total{topic="raw-products"}[5m])

# Соотношение создания/обогащения
sum(kafka_messages_consumed_total{status="success"}) / 
sum(kafka_messages_consumed_total{status="enriched"})

# Ошибки
rate(kafka_messages_consumed_total{status="error"}[5m])
```

### Логи

```bash
# Просмотр аудита обогащения
kubectl logs -l app=worker-raw-products | grep "MDM processing"
```

## Тестирование

```bash
# Unit тесты
pytest tests/unit/test_product_refinery.py -v

# Интеграционные тесты
pytest tests/integration/test_mdm_pipeline.py -v
```

## Что это даёт?

1. **Самообогащение**: Чем больше магазинов парсишь — тем полнее карточка
2. **Чистота данных**: "Ротбанд" и "Штукатурка Ротбанд" склеятся в один товар
3. **Связи**: Автоматическая привязка к производителям
4. **Аудит**: Полная история изменений каждого товара
5. **Масштабируемость**: Vector Search для миллионов товаров
