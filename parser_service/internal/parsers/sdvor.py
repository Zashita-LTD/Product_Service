"""
Строительный Двор Parser.

Parser for sdvor.com construction materials store.
Uses classic HTML parsing without SPA complexity.
"""

from typing import List, Optional, AsyncGenerator
from playwright.async_api import Page

from parser_service.internal.parsers.base import BaseParser
from parser_service.internal.models.product import RawProduct


class SdvorParser(BaseParser):
    """Parser for sdvor.com"""

    def __init__(self, base_url: str = "https://sdvor.com"):
        """
        Initialize Sdvor parser.

        Args:
            base_url: Base URL for the store.
        """
        self.base_url = base_url

    @property
    def name(self) -> str:
        return "sdvor.com"

    async def get_category_urls(self, page: Page) -> List[str]:
        """Get category URLs from Sdvor catalog."""
        await page.goto(f"{self.base_url}/catalog/")
        await page.wait_for_load_state("networkidle")

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
        """Get product URLs from Sdvor category with pagination."""
        current_page = 1

        while True:
            # Navigate to category page with pagination
            page_url = f"{category_url}?page={current_page}"
            await page.goto(page_url)
            await page.wait_for_load_state("networkidle")

            # Extract product links
            product_elements = await page.query_selector_all('a[href*="/product/"]')

            if not product_elements:
                break

            seen_urls = set()
            for elem in product_elements:
                href = await elem.get_attribute("href")
                if href:
                    full_url = f"{self.base_url}{href}" if href.startswith("/") else href
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        yield full_url

            # Check if there's a next page link
            next_button = await page.query_selector('a.next, a[rel="next"], .pagination a:has-text("Следующая")')
            if not next_button:
                break

            current_page += 1

    async def parse_product(self, page: Page, url: str) -> Optional[RawProduct]:
        """Parse Sdvor product page."""
        try:
            await page.goto(url)
            await page.wait_for_load_state("networkidle")

            # Try JSON-LD first
            json_ld = await self.extract_json_ld(page)
            if json_ld:
                product = self._parse_from_json_ld(url, json_ld)
                if product and product.name_original:
                    return product

            # Fallback to HTML parsing (primary method for classic HTML sites)
            return await self._parse_from_html(page, url)

        except Exception as e:
            print(f"Failed to parse Sdvor product {url}: {e}")
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
        """Parse product from HTML."""
        product = RawProduct(
            source_url=url,
            source_name=self.name,
        )

        # Extract product name
        name_selectors = ["h1.product-title", "h1.product-name", "h1", ".product-title"]
        for selector in name_selectors:
            name_elem = await page.query_selector(selector)
            if name_elem:
                product.name_original = (await name_elem.inner_text()).strip()
                break

        # Extract brand
        brand_selectors = [".product-brand", '[itemprop="brand"]', ".brand-name"]
        for selector in brand_selectors:
            brand_elem = await page.query_selector(selector)
            if brand_elem:
                brand_text = await brand_elem.inner_text()
                product.brand = brand_text.strip()
                break

        # Extract price
        price_selectors = [".product-price", '[itemprop="price"]', ".price-value", "span.price"]
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
        availability_elem = await page.query_selector('.availability, .stock-status, [itemprop="availability"]')
        if availability_elem:
            availability_text = (await availability_elem.inner_text()).lower()
            if "в наличии" in availability_text or "stock" in availability_text:
                product.availability = "in_stock"
            elif "нет в наличии" in availability_text or "out" in availability_text:
                product.availability = "out_of_stock"

        # Extract images from gallery
        img_elements = await page.query_selector_all('.product-gallery img, .product-images img, [itemprop="image"]')
        images = []
        for img in img_elements:
            src = await img.get_attribute("src") or await img.get_attribute("data-src")
            if src and "placeholder" not in src and "no-image" not in src:
                # Convert relative URLs to absolute
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = self.base_url + src
                images.append(src)
        product.images = images if images else None

        # Extract breadcrumbs
        breadcrumb_selectors = [".breadcrumbs a", '[itemprop="itemListElement"]', ".breadcrumb-item"]
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

        # Extract attributes from table or dl
        attributes = []

        # Try table format: <table class="properties">
        table_rows = await page.query_selector_all("table.properties tr, table.specifications tr, table.attributes tr")
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

        # Try <dl> format if no table found
        if not attributes:
            dl_elements = await page.query_selector_all("dl.properties, dl.specifications")
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

        product.attributes = attributes if attributes else None

        # Extract documents (PDFs, certificates, manuals)
        doc_elements = await page.query_selector_all('a[href$=".pdf"], .documents a, .certificates a')
        documents = []
        for doc_elem in doc_elements:
            href = await doc_elem.get_attribute("href")
            title = (await doc_elem.inner_text()).strip()
            if href:
                # Convert relative URLs to absolute
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
