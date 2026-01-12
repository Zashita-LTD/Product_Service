"""
Petrovich.ru parser implementation.

Extracts product data from moscow.petrovich.ru using multiple data sources:
1. JSON-LD (Schema.org) - highest priority
2. __NEXT_DATA__ - Next.js SSR data
3. HTML parsing - fallback
"""
import re
import json
import asyncio
import random
from typing import List, Dict, Any, Optional, AsyncIterator, Set
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from internal.parsers.base import BaseParser
from internal.models.product import (
    RawProduct,
    ProductAttribute,
    ProductAttributeType,
    ProductPrice,
    ProductAvailability,
    AvailabilityStatus,
    ProductImage,
    ProductDocument,
    DocumentType,
)
from pkg.logger.logger import get_logger
from config.settings import Settings


logger = get_logger(__name__)


class PetrovichParser(BaseParser):
    """
    Parser for moscow.petrovich.ru.
    
    Implements smart scraping with multiple data extraction methods.
    """
    
    def __init__(self, browser, kafka_producer, settings: Settings):
        """
        Initialize Petrovich parser.
        
        Args:
            browser: Browser instance.
            kafka_producer: Kafka producer.
            settings: Application settings.
        """
        super().__init__(browser, kafka_producer)
        self._settings = settings
        self._base_url = settings.petrovich_base_url
        self._products_parsed = 0
        self._visited_urls: Set[str] = set()
    
    @property
    def source_name(self) -> str:
        """Get source name."""
        return "moscow.petrovich.ru"
    
    async def parse_catalog(self) -> AsyncIterator[RawProduct]:
        """
        Parse the entire catalog by traversing categories.
        
        Yields:
            Raw product data.
        """
        logger.info("Starting catalog parsing", base_url=self._base_url)
        
        # Start from catalog page
        catalog_url = urljoin(self._base_url, "/catalog/")
        
        try:
            # Get category URLs
            category_urls = await self._get_category_urls(catalog_url)
            logger.info(f"Found {len(category_urls)} categories")
            
            # Process each category
            for category_url in category_urls:
                if self._products_parsed >= self._settings.max_products_per_run:
                    logger.info(
                        "Max products limit reached",
                        limit=self._settings.max_products_per_run,
                    )
                    break
                
                logger.info("Processing category", url=category_url)
                
                async for product in self._parse_category(category_url):
                    yield product
                    self._products_parsed += 1
                    
                    if self._products_parsed >= self._settings.max_products_per_run:
                        break
                
                # Random delay between categories
                await self._random_delay()
        
        except Exception as e:
            logger.error(f"Error parsing catalog: {e}", exc_info=True)
            await self._browser.handle_error(e)
            raise
        
        logger.info(
            "Catalog parsing completed",
            total_products=self._products_parsed,
        )
    
    async def _get_category_urls(self, catalog_url: str) -> List[str]:
        """
        Extract category URLs from catalog page.
        
        Args:
            catalog_url: Catalog page URL.
            
        Returns:
            List of category URLs.
        """
        page = await self._browser.new_page()
        
        try:
            await page.goto(catalog_url, wait_until="networkidle", timeout=30000)
            await self._random_delay(0.5, 2.0)
            
            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")
            
            # Find category links (adjust selectors based on actual site structure)
            category_links = []
            
            # Common patterns for category links
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                
                # Look for catalog category links
                if "/catalog/" in href and href not in category_links:
                    full_url = urljoin(self._base_url, href)
                    
                    # Skip if it's just the catalog root
                    if full_url != catalog_url:
                        category_links.append(full_url)
            
            return category_links[:50]  # Limit to avoid too many categories
            
        except Exception as e:
            logger.error(f"Error getting category URLs: {e}", exc_info=True)
            await self._browser.handle_error(e)
            return []
        finally:
            await page.close()
    
    async def _parse_category(self, category_url: str) -> AsyncIterator[RawProduct]:
        """
        Parse all products in a category.
        
        Args:
            category_url: Category page URL.
            
        Yields:
            Raw product data.
        """
        page = await self._browser.new_page()
        page_num = 1
        
        try:
            while True:
                # Navigate to category page
                page_url = f"{category_url}?page={page_num}" if page_num > 1 else category_url
                
                logger.info("Parsing category page", url=page_url, page=page_num)
                
                try:
                    await page.goto(page_url, wait_until="networkidle", timeout=30000)
                    await self._random_delay()
                except PlaywrightTimeout:
                    logger.warning(f"Timeout loading category page {page_url}")
                    await self._browser.handle_error(Exception("Timeout"))
                    break
                
                content = await page.content()
                soup = BeautifulSoup(content, "html.parser")
                
                # Extract product URLs from the page
                product_urls = self._extract_product_urls(soup)
                
                if not product_urls:
                    logger.info("No more products found in category")
                    break
                
                logger.info(f"Found {len(product_urls)} products on page {page_num}")
                
                # Parse each product
                for product_url in product_urls:
                    if product_url in self._visited_urls:
                        continue
                    
                    self._visited_urls.add(product_url)
                    
                    try:
                        product = await self.parse_product(product_url)
                        yield product
                        
                        # Send to Kafka
                        await self._kafka.send_product(product)
                        
                        await self._random_delay()
                        
                    except Exception as e:
                        logger.error(
                            f"Error parsing product {product_url}: {e}",
                            exc_info=True,
                        )
                        continue
                
                # Check for next page
                if not self._has_next_page(soup):
                    break
                
                page_num += 1
                
        finally:
            await page.close()
    
    def _extract_product_urls(self, soup: BeautifulSoup) -> List[str]:
        """
        Extract product URLs from category page.
        
        Args:
            soup: BeautifulSoup object.
            
        Returns:
            List of product URLs.
        """
        product_urls = []
        
        # Look for product links (adjust selectors based on actual site)
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            
            # Product URLs typically contain /product/ or similar
            if "/product/" in href or re.match(r"/p/\d+", href):
                full_url = urljoin(self._base_url, href)
                if full_url not in product_urls:
                    product_urls.append(full_url)
        
        return product_urls
    
    def _has_next_page(self, soup: BeautifulSoup) -> bool:
        """
        Check if there's a next page.
        
        Args:
            soup: BeautifulSoup object.
            
        Returns:
            True if next page exists.
        """
        # Look for pagination next button
        next_button = soup.find("a", {"rel": "next"})
        if next_button:
            return True
        
        # Alternative: look for "Next" or "Следующая" text
        for link in soup.find_all("a", href=True):
            text = link.get_text(strip=True).lower()
            if "next" in text or "следующая" in text or "далее" in text:
                return True
        
        return False
    
    async def parse_product(self, url: str) -> RawProduct:
        """
        Parse a single product page.
        
        Priority:
        1. JSON-LD (Schema.org)
        2. __NEXT_DATA__
        3. HTML parsing
        
        Args:
            url: Product page URL.
            
        Returns:
            Raw product data.
        """
        logger.info("Parsing product", url=url)
        
        page = await self._browser.new_page()
        
        try:
            # Navigate to product page with retries
            for attempt in range(self._settings.max_retries):
                try:
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    break
                except PlaywrightTimeout:
                    if attempt == self._settings.max_retries - 1:
                        raise
                    logger.warning(f"Timeout on attempt {attempt + 1}, retrying...")
                    await self._random_delay(2.0, 5.0)
                    await self._browser.handle_error(Exception("Timeout"))
            
            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")
            
            # Try extraction methods in priority order
            product_data = (
                await self._extract_from_json_ld(soup)
                or await self._extract_from_next_data(soup)
                or await self._extract_from_html(soup)
            )
            
            if not product_data:
                raise ValueError("No data could be extracted from product page")
            
            # Build RawProduct
            product = RawProduct(
                source_url=url,
                source_name=self.source_name,
                **product_data,
            )
            
            logger.info(
                "Product parsed successfully",
                url=url,
                name=product.name_original,
                attributes_count=len(product.attributes),
                documents_count=len(product.documents),
            )
            
            return product
            
        finally:
            await page.close()
    
    async def _extract_from_json_ld(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """
        Extract data from JSON-LD (Schema.org).
        
        Args:
            soup: BeautifulSoup object.
            
        Returns:
            Product data dictionary or None.
        """
        try:
            # Find JSON-LD script tags
            json_ld_scripts = soup.find_all("script", type="application/ld+json")
            
            for script in json_ld_scripts:
                try:
                    data = json.loads(script.string)
                    
                    # Handle both single object and array
                    if isinstance(data, list):
                        for item in data:
                            if item.get("@type") == "Product":
                                return self._parse_json_ld_product(item)
                    elif data.get("@type") == "Product":
                        return self._parse_json_ld_product(data)
                        
                except json.JSONDecodeError:
                    continue
            
            logger.debug("No valid JSON-LD Product data found")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting JSON-LD: {e}", exc_info=True)
            return None
    
    def _parse_json_ld_product(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Schema.org Product data."""
        result = {
            "name_original": data.get("name", ""),
            "schema_org_data": data,
        }
        
        # Brand
        if "brand" in data:
            brand = data["brand"]
            if isinstance(brand, dict):
                result["brand"] = brand.get("name", "")
            else:
                result["brand"] = str(brand)
        
        # Description
        if "description" in data:
            result["description_full"] = data["description"]
        
        # SKU
        if "sku" in data:
            result["sku"] = data["sku"]
        
        # Images
        images = []
        if "image" in data:
            image_data = data["image"]
            if isinstance(image_data, list):
                for idx, img_url in enumerate(image_data):
                    images.append(ProductImage(url=img_url, position=idx))
            elif isinstance(image_data, str):
                images.append(ProductImage(url=image_data, position=0))
        result["images"] = images
        
        # Price
        if "offers" in data:
            offers = data["offers"]
            if isinstance(offers, dict):
                price_value = offers.get("price")
                if price_value:
                    result["price"] = ProductPrice(
                        current=float(price_value),
                        currency=offers.get("priceCurrency", "RUB"),
                    )
                
                # Availability
                availability_str = offers.get("availability", "")
                status = AvailabilityStatus.UNKNOWN
                if "InStock" in availability_str:
                    status = AvailabilityStatus.IN_STOCK
                elif "OutOfStock" in availability_str:
                    status = AvailabilityStatus.OUT_OF_STOCK
                
                result["availability"] = ProductAvailability(status=status)
        
        return result
    
    async def _extract_from_next_data(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """
        Extract data from __NEXT_DATA__ (Next.js SSR).
        
        Args:
            soup: BeautifulSoup object.
            
        Returns:
            Product data dictionary or None.
        """
        try:
            next_data_script = soup.find("script", id="__NEXT_DATA__")
            
            if not next_data_script:
                logger.debug("No __NEXT_DATA__ found")
                return None
            
            data = json.loads(next_data_script.string)
            
            # Navigate to product data (structure depends on site)
            # This is a generic implementation - adjust based on actual structure
            page_props = data.get("props", {}).get("pageProps", {})
            product_data = page_props.get("product", {})
            
            if not product_data:
                return None
            
            logger.info("Extracting from __NEXT_DATA__")
            
            result = {
                "name_original": product_data.get("name", ""),
                "brand": product_data.get("brand", ""),
                "description_full": product_data.get("description", ""),
                "sku": product_data.get("sku", "") or product_data.get("article", ""),
            }
            
            # Attributes
            attributes = []
            if "attributes" in product_data:
                for attr in product_data["attributes"]:
                    attributes.append(ProductAttribute(
                        name=attr.get("name", ""),
                        value=str(attr.get("value", "")),
                        type=ProductAttributeType.TEXT,
                    ))
            result["attributes"] = attributes
            
            # Price
            if "price" in product_data:
                result["price"] = ProductPrice(
                    current=float(product_data["price"]),
                    currency="RUB",
                )
            
            # Images
            images = []
            if "images" in product_data:
                for idx, img in enumerate(product_data["images"]):
                    if isinstance(img, dict):
                        img_url = img.get("url", "")
                    else:
                        img_url = str(img)
                    if img_url:
                        images.append(ProductImage(url=img_url, position=idx))
            result["images"] = images
            
            return result
            
        except Exception as e:
            logger.error(f"Error extracting __NEXT_DATA__: {e}", exc_info=True)
            return None
    
    async def _extract_from_html(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """
        Extract data from HTML (fallback).
        
        Args:
            soup: BeautifulSoup object.
            
        Returns:
            Product data dictionary or None.
        """
        try:
            logger.info("Falling back to HTML parsing")
            
            result = {}
            
            # Try to find product name
            # Common selectors for product name
            name_selectors = [
                ("h1", {}),
                ("h1", {"class": re.compile(r"product.*title", re.I)}),
                ("div", {"class": re.compile(r"product.*name", re.I)}),
            ]
            
            for tag, attrs in name_selectors:
                element = soup.find(tag, attrs)
                if element:
                    result["name_original"] = element.get_text(strip=True)
                    break
            
            if not result.get("name_original"):
                return None
            
            # Try to find price
            price_patterns = [
                re.compile(r"price", re.I),
                re.compile(r"cost", re.I),
                re.compile(r"цена", re.I),
            ]
            
            for pattern in price_patterns:
                price_elem = soup.find(text=pattern)
                if price_elem:
                    # Look for numbers nearby
                    parent = price_elem.parent
                    if parent:
                        text = parent.get_text()
                        price_match = re.search(r"(\d+[\s,]?\d*)", text)
                        if price_match:
                            price_str = price_match.group(1).replace(",", "").replace(" ", "")
                            result["price"] = ProductPrice(
                                current=float(price_str),
                                currency="RUB",
                            )
                            break
            
            # Try to find attributes in table
            attributes = []
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    cells = row.find_all(["td", "th"])
                    if len(cells) >= 2:
                        name = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        if name and value:
                            attributes.append(ProductAttribute(
                                name=name,
                                value=value,
                                type=ProductAttributeType.TEXT,
                            ))
            
            result["attributes"] = attributes
            
            # Try to find images
            images = []
            img_tags = soup.find_all("img", src=True)
            for idx, img in enumerate(img_tags):
                src = img.get("src", "")
                if src and ("/product" in src or "/catalog" in src or "cdn" in src):
                    try:
                        full_url = urljoin(self._base_url, src)
                        images.append(ProductImage(url=full_url, position=idx))
                    except Exception:
                        # Skip invalid image URLs
                        pass
            
            result["images"] = images[:10]  # Limit to 10 images
            
            # Try to find documents (PDFs, etc.)
            documents = []
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if href.endswith(".pdf") or "certificate" in href.lower() or "manual" in href.lower():
                    try:
                        full_url = urljoin(self._base_url, href)
                        doc_type = DocumentType.CERTIFICATE if "certificate" in href.lower() else DocumentType.MANUAL
                        documents.append(ProductDocument(
                            url=full_url,
                            title=link.get_text(strip=True),
                            type=doc_type,
                            file_format="pdf" if href.endswith(".pdf") else None,
                        ))
                    except Exception:
                        # Skip invalid document URLs
                        pass
            
            result["documents"] = documents
            
            return result
            
        except Exception as e:
            logger.error(f"Error extracting from HTML: {e}", exc_info=True)
            return None
    
    async def _random_delay(self, min_sec: Optional[float] = None, max_sec: Optional[float] = None) -> None:
        """
        Random delay to avoid detection.
        
        Args:
            min_sec: Minimum delay in seconds (uses settings if None).
            max_sec: Maximum delay in seconds (uses settings if None).
        """
        min_delay = min_sec if min_sec is not None else self._settings.min_delay_seconds
        max_delay = max_sec if max_sec is not None else self._settings.max_delay_seconds
        
        delay = random.uniform(min_delay, max_delay)
        logger.debug(f"Sleeping for {delay:.2f} seconds")
        await asyncio.sleep(delay)
