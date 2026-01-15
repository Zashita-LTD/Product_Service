"""
Parser Service - Main Entry Point.

Smart web scraper for creating Digital Twins from moscow.petrovich.ru.
"""
import asyncio
import signal
import sys
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, "/app")

from internal.browser.instance import BrowserInstance
from internal.kafka.producer import KafkaProducer
from internal.parsers.petrovich import PetrovichParser
from config.settings import get_settings
from pkg.logger.logger import setup_logging, get_logger


# Global flag for graceful shutdown
shutdown_event = asyncio.Event()


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger = get_logger(__name__)
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()


async def main():
    """Main parser service execution."""
    # Load settings
    settings = get_settings()
    
    # Setup logging
    setup_logging(
        level=settings.log_level,
        json_format=(settings.log_format == "json"),
    )
    
    logger = get_logger(__name__)
    logger.info(
        "Parser Service starting",
        version="1.0.0",
        base_url=settings.petrovich_base_url,
        kafka_servers=settings.kafka_bootstrap_servers,
        max_products=settings.max_products_per_run,
    )
    
    # Initialize components
    browser = None
    kafka = None
    
    try:
        # Initialize browser
        logger.info("Initializing browser...")
        browser = BrowserInstance(settings)
        await browser.start()
        
        # Initialize Kafka producer
        logger.info("Initializing Kafka producer...")
        kafka = KafkaProducer(settings)
        await kafka.start()
        
        # Initialize parser
        logger.info("Initializing Petrovich parser...")
        parser = PetrovichParser(browser, kafka, settings)
        
        # Parse catalog
        logger.info("Starting catalog parsing...")
        products_count = 0
        
        async for product in parser.parse_catalog():
            products_count += 1
            
            # Check for shutdown signal
            if shutdown_event.is_set():
                logger.info("Shutdown signal received, stopping parsing...")
                break
        
        # Flush remaining messages
        logger.info("Flushing Kafka messages...")
        await kafka.flush()
        
        logger.info(
            "Parsing completed successfully",
            total_products=products_count,
            messages_sent=kafka.messages_sent,
        )
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Cleanup
        if kafka:
            logger.info("Stopping Kafka producer...")
            await kafka.stop()
        
        if browser:
            logger.info("Stopping browser...")
            await browser.stop()
        
        logger.info("Parser Service stopped")


async def scheduler_loop():
    """
    Run parser on schedule.
    
    Executes parsing at configured intervals.
    """
    settings = get_settings()
    logger = get_logger(__name__)
    
    logger.info(
        "Starting scheduler",
        interval_seconds=settings.parsing_interval_seconds,
    )
    
    while not shutdown_event.is_set():
        try:
            # Run parsing
            await main()
            
            # Wait for next run
            if not shutdown_event.is_set():
                logger.info(
                    f"Waiting {settings.parsing_interval_seconds} seconds until next run..."
                )
                
                try:
                    await asyncio.wait_for(
                        shutdown_event.wait(),
                        timeout=settings.parsing_interval_seconds,
                    )
                except asyncio.TimeoutError:
                    # Timeout is expected - time for next run
                    pass
                
        except Exception as e:
            logger.error(f"Error in scheduler loop: {e}", exc_info=True)
            
            # Wait before retry
            if not shutdown_event.is_set():
                logger.info("Waiting 60 seconds before retry...")
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=60)
                except asyncio.TimeoutError:
                    pass


if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Determine if we should run once or on schedule
    # For now, run on schedule - can be controlled via env var in future
    settings = get_settings()
    
    if settings.parsing_interval_seconds > 0:
        # Run on schedule
        asyncio.run(scheduler_loop())
    else:
        # Run once
        asyncio.run(main())
