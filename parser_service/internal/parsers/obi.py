"""
OBI Parser.

Parser for obi.ru construction materials store.
Handles React SPA with dynamic content loading.
"""

from typing import List, Optional, AsyncGenerator
from playwright.async_api import Page

from parser_service.internal.parsers.base import BaseParser
from parser_service.internal.models.product import RawProduct


class ObiParser(BaseParser):
    """Parser for obi.ru"""

    def __init__(self, base_url: str = "https://obi.ru"):
        """
        Initialize OBI parser.

        Args:
            base_url: Base URL for the store.
        """
        self.base_url = base_url

    @property
    def name(self) -> str:
        return "obi.ru"

    async def get_category_urls(self, page: Page) -> List[str]:
        """Get category URLs from OBI catalog."""
        await page.goto(f"{self.base_url}/catalog/")
        await page.wait_for_load_state("networkidle")

        # Wait for React to render categories
        try:
            await page.wait_for_selector('a[href*="/catalog/"]', timeout=10000)
        except:
            pass

        # Extract category links
        category_elements = await page.query_selector_all('a[href*="/catalog/"]')
        urls = []

        for elem in category_elements:
            href = await elem.get_attribute("href")
            if href and href.startswith("/catalog/") and href != "/catalog/":
                full_url = f"{self.base_url}{href}" if href.startswith("/") else href
                if full_url not in urls and "/product/" not in full_url:
                    urls.append(full_url)

        return urls

    async def get_product_urls(self, page: Page, category_url: str) -> AsyncGenerator[str, None]:
        """Get product URLs from OBI category with pagination."""
        current_page = 1

        while True:
            # Navigate to category page
            page_url = f"{category_url}?page={current_page}"
            await page.goto(page_url)
            await page.wait_for_load_state("networkidle")

            # Wait for React to render product cards
            try:
                await page.wait_for_selector('.product-card, [data-testid="product-card"]', timeout=10000)
            except:
                # No products found, end pagination
                break

            # Give React time to fully render
            await page.wait_for_timeout(1000)

            # Extract product links
            product_elements = await page.query_selector_all('a[href*="/product/"], .product-card a')

            if not product_elements:
                break

            seen_urls = set()
            for elem in product_elements:
                href = await elem.get_attribute("href")
                if href and "/product/" in href:
                    full_url = f"{self.base_url}{href}" if href.startswith("/") else href
                    # Remove query parameters for deduplication
                    base_url = full_url.split("?")[0]
                    if base_url not in seen_urls:
                        seen_urls.add(base_url)
                        yield base_url

            if not seen_urls:
                break

            # Check if there's a next page button
            next_button = await page.query_selector(
                'button[aria-label="Next page"], '
                + 'a[aria-label="Next page"], '
                + '.pagination button:has-text("Следующая"), '
                + '.pagination a:has-text("Следующая")'
            )
            if not next_button:
                break

            is_disabled = await next_button.get_attribute("disabled") or await next_button.get_attribute(
                "aria-disabled"
            )
            if is_disabled == "true" or is_disabled is not None:
                break

            current_page += 1

    async def parse_product(self, page: Page, url: str) -> Optional[RawProduct]:
        """Parse OBI product page."""
        try:
            await page.goto(url)
            await page.wait_for_load_state("networkidle")

            # Wait for React to render the product content
            try:
                await page.wait_for_selector('h1, [data-testid="product-title"]', timeout=10000)
            except:
                print(f"Timeout waiting for product content on {url}")
                return None

            # Give React time to fully render
            await page.wait_for_timeout(1000)

            # Try JSON-LD first (may be present even in SPA)
            json_ld = await self.extract_json_ld(page)
            if json_ld:
                product = self._parse_from_json_ld(url, json_ld)
                if product and product.name_original:
                    return product

            # Fallback to HTML parsing after React render
            return await self._parse_from_html(page, url)

        except Exception as e:
            print(f"Failed to parse OBI product {url}: {e}")
            return None

    def _parse_from_json_ld(self, url: str, data: dict) -> RawProduct:
        """Parse product from JSON-LD data."""
        product = RawProduct(
            source_url=url,
            source_name=self.name,
            schema_org_data=data,
        )

        # Handle both single product and array of JSON-LD objects
        product_data = data
        if isinstance(data, list):
            product_data = next((item for item in data if item.get("@type") == "Product"), data[0] if data else {})

        if product_data.get("@type") == "Product":
            product.name_original = product_data.get("name", "")

            # Brand
            brand = product_data.get("brand", {})
            if isinstance(brand, dict):
                product.brand = brand.get("name")
            else:
                product.brand = brand

            # Price
            offers = product_data.get("offers", {})
            if isinstance(offers, dict):
                product.price_amount = float(offers.get("price", 0)) if offers.get("price") else None
                product.price_currency = offers.get("priceCurrency", "RUB")
                availability = offers.get("availability", "")
                if "InStock" in availability:
                    product.availability = "in_stock"
                elif "OutOfStock" in availability:
                    product.availability = "out_of_stock"

            # Images
            images = product_data.get("image", [])
            if isinstance(images, str):
                product.images = [images]
            elif isinstance(images, list):
                product.images = images

        return product

    async def _parse_from_html(self, page: Page, url: str) -> RawProduct:
        """Parse product from HTML after React rendering."""
        product = RawProduct(
            source_url=url,
            source_name=self.name,
        )

        # Extract product name
        name_selectors = ['h1[data-testid="product-title"]', "h1.product-title", "h1.product-name", "h1"]
        for selector in name_selectors:
            name_elem = await page.query_selector(selector)
            if name_elem:
                product.name_original = (await name_elem.inner_text()).strip()
                break

        # Extract brand
        brand_selectors = ['[data-testid="product-brand"]', ".product-brand", '[itemprop="brand"]']
        for selector in brand_selectors:
            brand_elem = await page.query_selector(selector)
            if brand_elem:
                brand_text = await brand_elem.inner_text()
                product.brand = brand_text.strip()
                break

        # Extract price
        price_selectors = [
            '[data-testid="product-price"]',
            ".product-price",
            '[itemprop="price"]',
            "span.price-value",
            ".price",
        ]
        for selector in price_selectors:
            price_elem = await page.query_selector(selector)
            if price_elem:
                price_text = await price_elem.get_attribute("content") or await price_elem.inner_text()
                try:
                    # Clean price text
                    price_clean = price_text.replace("₽", "").replace("руб", "").replace(" ", "").replace(",", ".")
                    product.price_amount = float(price_clean)
                    break
                except:
                    pass

        # Extract availability
        availability_selectors = [
            '[data-testid="availability"]',
            ".availability",
            ".stock-status",
            '[itemprop="availability"]',
        ]
        for selector in availability_selectors:
            availability_elem = await page.query_selector(selector)
            if availability_elem:
                availability_text = (await availability_elem.inner_text()).lower()
                if "в наличии" in availability_text or "stock" in availability_text:
                    product.availability = "in_stock"
                elif "нет в наличии" in availability_text or "out" in availability_text:
                    product.availability = "out_of_stock"
                break

        # Extract images
        img_selectors = [
            '[data-testid="product-image"]',
            ".product-gallery img",
            ".product-images img",
            '[itemprop="image"]',
        ]
        images = []
        for selector in img_selectors:
            img_elements = await page.query_selector_all(selector)
            if img_elements:
                for img in img_elements:
                    src = await img.get_attribute("src") or await img.get_attribute("data-src")
                    if src and "placeholder" not in src and "no-image" not in src:
                        if src.startswith("//"):
                            src = "https:" + src
                        elif src.startswith("/"):
                            src = self.base_url + src
                        images.append(src)
                if images:
                    break
        product.images = images if images else None

        # Extract breadcrumbs
        breadcrumb_selectors = ['[data-testid="breadcrumb"]', ".breadcrumbs a", '[itemprop="itemListElement"]']
        breadcrumbs = []
        for selector in breadcrumb_selectors:
            breadcrumb_elements = await page.query_selector_all(selector)
            if breadcrumb_elements:
                for elem in breadcrumb_elements:
                    text_elem = await elem.query_selector('[itemprop="name"]') or elem
                    text = (await text_elem.inner_text()).strip()
                    if text and text not in breadcrumbs:
                        breadcrumbs.append(text)
                if breadcrumbs:
                    break
        product.category_breadcrumbs = breadcrumbs if breadcrumbs else None

        # Extract attributes - may need to click on "Характеристики" tab
        # Try to click on specifications tab if it exists
        specs_tab_selectors = [
            'button:has-text("Характеристики")',
            'a:has-text("Характеристики")',
            '[data-testid="specifications-tab"]',
        ]
        for selector in specs_tab_selectors:
            tab_elem = await page.query_selector(selector)
            if tab_elem:
                try:
                    await tab_elem.click()
                    await page.wait_for_timeout(500)  # Wait for tab content to load
                    break
                except:
                    pass

        # Extract attributes
        attributes = []

        # Try table format
        table_selectors = [
            '[data-testid="specifications-table"] tr',
            "table.specifications tr",
            "table.attributes tr",
            ".specifications-table tr",
        ]
        for selector in table_selectors:
            table_rows = await page.query_selector_all(selector)
            if table_rows:
                for row in table_rows:
                    cells = await row.query_selector_all("td, th")
                    if len(cells) >= 2:
                        name = (await cells[0].inner_text()).strip()
                        value = (await cells[1].inner_text()).strip()
                        if name and value:
                            attributes.append(
                                {
                                    "name": name,
                                    "value": value,
                                    "unit": "",
                                }
                            )
                if attributes:
                    break

        # Try dl format if no table found
        if not attributes:
            dl_selectors = ["dl.specifications", "dl.attributes", '[data-testid="specifications-list"]']
            for selector in dl_selectors:
                dl_elements = await page.query_selector_all(selector)
                for dl in dl_elements:
                    dt_elements = await dl.query_selector_all("dt")
                    dd_elements = await dl.query_selector_all("dd")
                    for dt, dd in zip(dt_elements, dd_elements):
                        name = (await dt.inner_text()).strip()
                        value = (await dd.inner_text()).strip()
                        if name and value:
                            attributes.append(
                                {
                                    "name": name,
                                    "value": value,
                                    "unit": "",
                                }
                            )
                if attributes:
                    break

        product.attributes = attributes if attributes else None

        # Extract documents
        doc_elements = await page.query_selector_all('a[href$=".pdf"], .documents a, [data-testid="document-link"]')
        documents = []
        for doc_elem in doc_elements:
            href = await doc_elem.get_attribute("href")
            title = (await doc_elem.inner_text()).strip()
            if href:
                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    href = self.base_url + href

                doc_type = "manual"
                if "сертификат" in title.lower() or "certificate" in title.lower():
                    doc_type = "certificate"
                elif "инструкц" in title.lower() or "instruction" in title.lower():
                    doc_type = "manual"

                documents.append(
                    {
                        "type": doc_type,
                        "url": href,
                        "title": title or "Document",
                    }
                )
        product.documents = documents if documents else None

        return product
