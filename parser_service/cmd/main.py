"""
Parser Service Main Entry Point.

Orchestrates multiple store parsers and publishes scraped data to Kafka.
"""

import asyncio
import signal
from typing import List, Optional
import json
import time

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Browser, BrowserContext
from aiokafka import AIOKafkaProducer

from parser_service.internal.parsers.base import BaseParser
from parser_service.internal.parsers import (
    PetrovichParser,
    LeroyMerlinParser,
    SdvorParser,
    ObiParser,
)
from parser_service.internal.models.product import RawProduct
from parser_service.config.settings import settings
from parser_service.internal.metrics import (
    PAGES_PARSED,
    PRODUCTS_EXTRACTED,
    PARSE_DURATION,
    KAFKA_MESSAGES_PRODUCED,
)


# Load environment variables
load_dotenv()


class ParserScheduler:
    """
    Scheduler for running multiple parsers.

    Manages parser execution, data collection, and publishing to Kafka.
    """

    def __init__(self):
        """Initialize the parser scheduler."""
        self._running = False
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._producer: Optional[AIOKafkaProducer] = None
        self._parsers: List[BaseParser] = []

    async def start(self) -> None:
        """Start the parser scheduler."""
        print("Starting Parser Service...")
        print(f"Enabled parsers: {settings.ENABLED_PARSERS}")

        self._running = True

        # Initialize Playwright browser
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=settings.HEADLESS_BROWSER)
        self._context = await self._browser.new_context()
        print("Browser initialized")

        # Initialize Kafka producer
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await self._producer.start()
        print(f"Kafka producer started, publishing to topic: {settings.KAFKA_RAW_PRODUCTS_TOPIC}")

        # Initialize enabled parsers
        self._parsers = self._get_enabled_parsers()
        print(f"Initialized {len(self._parsers)} parsers")

        # Run parsers
        await self._run_parsers()

    async def stop(self) -> None:
        """Stop the parser scheduler."""
        print("Stopping Parser Service...")

        self._running = False

        if self._producer:
            await self._producer.stop()

        if self._context:
            await self._context.close()

        if self._browser:
            await self._browser.close()

        if hasattr(self, "_playwright"):
            await self._playwright.stop()

        print("Parser Service stopped")

    def _get_enabled_parsers(self) -> List[BaseParser]:
        """
        Get list of enabled parsers based on settings.

        Returns:
            List of initialized parser instances.
        """
        enabled = settings.get_enabled_parsers()
        parsers = []

        parser_map = {
            "petrovich": lambda: PetrovichParser(settings.PETROVICH_BASE_URL),
            "leroymerlin": lambda: LeroyMerlinParser(settings.LEROYMERLIN_BASE_URL),
            "sdvor": lambda: SdvorParser(settings.SDVOR_BASE_URL),
            "obi": lambda: ObiParser(settings.OBI_BASE_URL),
        }

        for parser_name in enabled:
            if parser_name in parser_map:
                parser = parser_map[parser_name]()
                parsers.append(parser)
                print(f"  ✓ Enabled parser: {parser.name}")
            else:
                print(f"  ✗ Unknown parser: {parser_name}")

        return parsers

    async def _run_parsers(self) -> None:
        """Run all enabled parsers."""
        for parser in self._parsers:
            if not self._running:
                break

            print(f"\n{'='*60}")
            print(f"Running parser: {parser.name}")
            print(f"{'='*60}")

            try:
                await self._run_parser(parser)
            except Exception as e:
                print(f"Error running parser {parser.name}: {e}")
                import traceback

                traceback.print_exc()

    async def _run_parser(self, parser: BaseParser) -> None:
        """
        Run a single parser.

        Args:
            parser: The parser instance to run.
        """
        page = await self._context.new_page()

        try:
            # Step 1: Get category URLs
            print(f"[{parser.name}] Fetching category URLs...")
            category_urls = await parser.get_category_urls(page)
            print(f"[{parser.name}] Found {len(category_urls)} categories")

            # Limit categories for demo/testing (can be removed for production)
            max_categories = 3
            if len(category_urls) > max_categories:
                print(f"[{parser.name}] Limiting to first {max_categories} categories for demo")
                category_urls = category_urls[:max_categories]

            # Step 2: Process each category
            for i, category_url in enumerate(category_urls, 1):
                if not self._running:
                    break

                print(f"\n[{parser.name}] Processing category {i}/{len(category_urls)}: {category_url}")
                
                # Track category page parsing
                PAGES_PARSED.labels(parser_name=parser.name, page_type='category').inc()

                # Step 3: Get product URLs from category
                product_count = 0
                max_products_per_category = 5  # Limit for demo

                async for product_url in parser.get_product_urls(page, category_url):
                    if not self._running or product_count >= max_products_per_category:
                        break

                    product_count += 1
                    print(f"  [{parser.name}] Product {product_count}: {product_url}")

                    # Step 4: Parse product page
                    product_page = await self._context.new_page()
                    try:
                        parse_start = time.time()
                        raw_product = await parser.parse_product(product_page, product_url)
                        parse_duration = time.time() - parse_start
                        
                        # Track parsing duration
                        PARSE_DURATION.labels(parser_name=parser.name, page_type='product').observe(parse_duration)
                        
                        # Track product page parsing
                        PAGES_PARSED.labels(parser_name=parser.name, page_type='product').inc()

                        if raw_product:
                            # Step 5: Publish to Kafka
                            await self._publish_product(raw_product)
                            print(f"    ✓ Published: {raw_product.name_original[:50]}...")
                            
                            # Track successful extraction
                            PRODUCTS_EXTRACTED.labels(parser_name=parser.name, status='success').inc()
                        else:
                            print("    ✗ Failed to parse product")
                            # Track failed extraction
                            PRODUCTS_EXTRACTED.labels(parser_name=parser.name, status='error').inc()

                    except Exception as e:
                        print(f"    ✗ Error parsing product: {e}")
                        # Track failed extraction
                        PRODUCTS_EXTRACTED.labels(parser_name=parser.name, status='error').inc()

                    finally:
                        await product_page.close()

                    # Rate limiting
                    await asyncio.sleep(1.0 / settings.REQUESTS_PER_SECOND)

                print(f"[{parser.name}] Processed {product_count} products from category")

        finally:
            await page.close()

    async def _publish_product(self, product: RawProduct) -> None:
        """
        Publish raw product to Kafka.

        Args:
            product: The raw product to publish.
        """
        event = product.to_kafka_event()

        try:
            await self._producer.send(
                settings.KAFKA_RAW_PRODUCTS_TOPIC,
                value=event,
            )
            # Track successful Kafka publish
            KAFKA_MESSAGES_PRODUCED.labels(status='success').inc()
        except Exception as e:
            # Track failed Kafka publish
            KAFKA_MESSAGES_PRODUCED.labels(status='error').inc()
            raise


async def main() -> None:
    """Main entry point."""
    scheduler = ParserScheduler()

    # Handle shutdown signals
    loop = asyncio.get_event_loop()

    def signal_handler() -> None:
        print("\nReceived shutdown signal")
        asyncio.create_task(scheduler.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await scheduler.start()
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received")
    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await scheduler.stop()


if __name__ == "__main__":
    asyncio.run(main())
