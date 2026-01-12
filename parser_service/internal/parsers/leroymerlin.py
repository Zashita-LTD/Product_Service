"""
Leroy Merlin Parser.

Parser for leroymerlin.ru construction materials store.
Focuses on extracting data from __NEXT_DATA__ (Next.js SSR).
"""

from typing import List, Optional, AsyncGenerator
from playwright.async_api import Page

from parser_service.internal.parsers.base import BaseParser
from parser_service.internal.models.product import RawProduct


class LeroyMerlinParser(BaseParser):
    """Parser for leroymerlin.ru"""

    def __init__(self, base_url: str = "https://leroymerlin.ru"):
        """
        Initialize Leroy Merlin parser.

        Args:
            base_url: Base URL for the store.
        """
        self.base_url = base_url

    @property
    def name(self) -> str:
        return "leroymerlin.ru"

    async def get_category_urls(self, page: Page) -> List[str]:
        """Get category URLs from Leroy Merlin catalog."""
        await page.goto(f"{self.base_url}/catalogue/")
        await page.wait_for_load_state("networkidle")

        # Extract category links from mega-menu
        category_elements = await page.query_selector_all('a[href*="/catalogue/"]')
        urls = []

        for elem in category_elements:
            href = await elem.get_attribute("href")
            if href and href.startswith("/catalogue/") and href != "/catalogue/":
                full_url = f"{self.base_url}{href}" if href.startswith("/") else href
                if full_url not in urls and "/product/" not in full_url:
                    urls.append(full_url)

        return urls

    async def get_product_urls(self, page: Page, category_url: str) -> AsyncGenerator[str, None]:
        """Get product URLs from Leroy Merlin category with pagination."""
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

            # Check if there's a next page button
            next_button = await page.query_selector('a[aria-label="Next page"], button[aria-label="Next page"]')
            if not next_button:
                break

            is_disabled = await next_button.get_attribute("disabled")
            if is_disabled:
                break

            current_page += 1

    async def parse_product(self, page: Page, url: str) -> Optional[RawProduct]:
        """Parse Leroy Merlin product page."""
        try:
            await page.goto(url)
            await page.wait_for_load_state("networkidle")

            # Priority 1: Extract from __NEXT_DATA__ (most complete data)
            next_data = await self.extract_next_data(page)
            if next_data:
                product = self._parse_from_next_data(url, next_data)
                if product and product.name_original:
                    return product

            # Priority 2: Try JSON-LD
            json_ld = await self.extract_json_ld(page)
            if json_ld:
                product = self._parse_from_json_ld(url, json_ld)
                if product and product.name_original:
                    return product

            # Priority 3: Fallback to HTML parsing
            return await self._parse_from_html(page, url)

        except Exception as e:
            print(f"Failed to parse Leroy Merlin product {url}: {e}")
            return None

    def _parse_from_next_data(self, url: str, data: dict) -> Optional[RawProduct]:
        """Parse product from __NEXT_DATA__."""
        product = RawProduct(
            source_url=url,
            source_name=self.name,
            next_data=data,
        )

        try:
            # Navigate through __NEXT_DATA__ structure
            # Structure varies, common path: props.pageProps.product
            page_props = data.get("props", {}).get("pageProps", {})
            product_data = page_props.get("product", {})

            if not product_data:
                # Try alternative structure
                product_data = page_props.get("initialState", {}).get("product", {})

            if product_data:
                product.name_original = product_data.get("name", product_data.get("title", ""))
                product.brand = (
                    product_data.get("brand", {}).get("name")
                    if isinstance(product_data.get("brand"), dict)
                    else product_data.get("brand")
                )

                # Price
                price_data = product_data.get("price", {})
                if isinstance(price_data, dict):
                    product.price_amount = price_data.get("value") or price_data.get("amount")
                    product.price_currency = price_data.get("currency", "RUB")
                elif isinstance(price_data, (int, float)):
                    product.price_amount = float(price_data)

                # Availability
                stock = product_data.get("stock", {})
                if isinstance(stock, dict):
                    in_stock = stock.get("available", False)
                    product.availability = "in_stock" if in_stock else "out_of_stock"

                # Images
                images = product_data.get("images", [])
                if images:
                    product.images = [img.get("url") or img for img in images if isinstance(img, (dict, str))]

                # Attributes/Specifications
                specs = product_data.get("specifications", []) or product_data.get("attributes", [])
                if specs:
                    attributes = []
                    for spec in specs:
                        if isinstance(spec, dict):
                            attributes.append(
                                {
                                    "name": spec.get("name", spec.get("title", "")),
                                    "value": spec.get("value", ""),
                                    "unit": spec.get("unit", ""),
                                }
                            )
                    product.attributes = attributes if attributes else None

                # Breadcrumbs
                breadcrumbs = product_data.get("breadcrumbs", []) or page_props.get("breadcrumbs", [])
                if breadcrumbs:
                    product.category_breadcrumbs = [
                        b.get("name") or b.get("title") for b in breadcrumbs if isinstance(b, dict)
                    ]

                # Documents (certificates, manuals)
                documents = product_data.get("documents", [])
                if documents:
                    docs = []
                    for doc in documents:
                        if isinstance(doc, dict):
                            docs.append(
                                {
                                    "type": doc.get("type", "document"),
                                    "url": doc.get("url", ""),
                                    "title": doc.get("title", ""),
                                }
                            )
                    product.documents = docs if docs else None

        except Exception as e:
            print(f"Error parsing __NEXT_DATA__: {e}")

        return product

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
        """Parse product from HTML as fallback."""
        product = RawProduct(
            source_url=url,
            source_name=self.name,
        )

        # Extract product name
        name_selectors = ["h1", '[data-testid="product-title"]', ".product-title"]
        for selector in name_selectors:
            name_elem = await page.query_selector(selector)
            if name_elem:
                product.name_original = (await name_elem.inner_text()).strip()
                break

        # Extract brand
        brand_elem = await page.query_selector('[data-testid="product-brand"], .product-brand')
        if brand_elem:
            product.brand = (await brand_elem.inner_text()).strip()

        # Extract price
        price_selectors = ['[data-testid="product-price"]', ".product-price", '[itemprop="price"]']
        for selector in price_selectors:
            price_elem = await page.query_selector(selector)
            if price_elem:
                price_text = await price_elem.get_attribute("content") or await price_elem.inner_text()
                try:
                    # Remove currency symbols and whitespace
                    price_clean = price_text.replace("₽", "").replace(" ", "").replace(",", ".")
                    product.price_amount = float(price_clean)
                    break
                except:
                    pass

        # Extract images
        img_elements = await page.query_selector_all('[data-testid="product-image"], .product-gallery img')
        images = []
        for img in img_elements:
            src = await img.get_attribute("src") or await img.get_attribute("data-src")
            if src and "placeholder" not in src:
                images.append(src)
        product.images = images if images else None

        # Extract breadcrumbs
        breadcrumb_elements = await page.query_selector_all('[data-testid="breadcrumb-item"], .breadcrumb-item')
        breadcrumbs = []
        for elem in breadcrumb_elements:
            text = (await elem.inner_text()).strip()
            if text:
                breadcrumbs.append(text)
        product.category_breadcrumbs = breadcrumbs if breadcrumbs else None

        # Extract attributes from table
        attr_rows = await page.query_selector_all('table.specifications tr, [data-testid="specification-row"]')
        attributes = []
        for row in attr_rows:
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
        product.attributes = attributes if attributes else None

        return product
