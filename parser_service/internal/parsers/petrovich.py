"""
Petrovich Parser.

Parser for petrovich.ru construction materials store.
"""
from typing import List, Optional, AsyncGenerator
from playwright.async_api import Page

from parser_service.internal.parsers.base import BaseParser
from parser_service.internal.models.product import RawProduct


class PetrovichParser(BaseParser):
    """Parser for petrovich.ru"""
    
    def __init__(self, base_url: str = "https://petrovich.ru"):
        """
        Initialize Petrovich parser.
        
        Args:
            base_url: Base URL for the store.
        """
        self.base_url = base_url
    
    @property
    def name(self) -> str:
        return "petrovich.ru"
    
    async def get_category_urls(self, page: Page) -> List[str]:
        """Get category URLs from Petrovich catalog."""
        await page.goto(f"{self.base_url}/catalog/")
        await page.wait_for_load_state("networkidle")
        
        # Extract category links
        category_elements = await page.query_selector_all('a[href*="/catalog/"]')
        urls = []
        
        for elem in category_elements:
            href = await elem.get_attribute("href")
            if href and href.startswith("/catalog/") and href != "/catalog/":
                full_url = f"{self.base_url}{href}" if href.startswith("/") else href
                if full_url not in urls:
                    urls.append(full_url)
        
        return urls
    
    async def get_product_urls(
        self, 
        page: Page, 
        category_url: str
    ) -> AsyncGenerator[str, None]:
        """Get product URLs from Petrovich category with pagination."""
        current_page = 1
        
        while True:
            # Navigate to category page
            page_url = f"{category_url}?page={current_page}"
            await page.goto(page_url)
            await page.wait_for_load_state("networkidle")
            
            # Extract product links
            product_elements = await page.query_selector_all('a[href*="/product/"]')
            
            if not product_elements:
                break
            
            for elem in product_elements:
                href = await elem.get_attribute("href")
                if href:
                    full_url = f"{self.base_url}{href}" if href.startswith("/") else href
                    yield full_url
            
            # Check if there's a next page
            next_button = await page.query_selector('a[rel="next"]')
            if not next_button:
                break
            
            current_page += 1
    
    async def parse_product(
        self, 
        page: Page, 
        url: str
    ) -> Optional[RawProduct]:
        """Parse Petrovich product page."""
        try:
            await page.goto(url)
            await page.wait_for_load_state("networkidle")
            
            # Try JSON-LD first
            json_ld = await self.extract_json_ld(page)
            if json_ld:
                return self._parse_from_json_ld(url, json_ld)
            
            # Fallback to HTML parsing
            return await self._parse_from_html(page, url)
            
        except Exception as e:
            print(f"Failed to parse Petrovich product {url}: {e}")
            return None
    
    def _parse_from_json_ld(self, url: str, data: dict) -> RawProduct:
        """Parse product from JSON-LD data."""
        product = RawProduct(
            source_url=url,
            source_name=self.name,
        )
        
        if data.get("@type") == "Product":
            product.name_original = data.get("name", "")
            product.brand = data.get("brand", {}).get("name") if isinstance(data.get("brand"), dict) else data.get("brand")
            
            # Price
            offers = data.get("offers", {})
            if isinstance(offers, dict):
                product.price_amount = offers.get("price")
                product.price_currency = offers.get("priceCurrency", "RUB")
                product.availability = offers.get("availability", "").split("/")[-1]
            
            # Images
            images = data.get("image", [])
            if isinstance(images, str):
                product.images = [images]
            elif isinstance(images, list):
                product.images = images
            
            product.schema_org_data = data
        
        return product
    
    async def _parse_from_html(self, page: Page, url: str) -> RawProduct:
        """Parse product from HTML."""
        product = RawProduct(
            source_url=url,
            source_name=self.name,
        )
        
        # Extract product name
        name_elem = await page.query_selector('h1')
        if name_elem:
            product.name_original = await name_elem.inner_text()
        
        # Extract brand
        brand_elem = await page.query_selector('[itemprop="brand"]')
        if brand_elem:
            product.brand = await brand_elem.inner_text()
        
        # Extract price
        price_elem = await page.query_selector('[itemprop="price"]')
        if price_elem:
            price_text = await price_elem.get_attribute("content") or await price_elem.inner_text()
            try:
                product.price_amount = float(price_text.replace(",", ".").replace(" ", ""))
            except:
                pass
        
        # Extract images
        img_elements = await page.query_selector_all('img[itemprop="image"]')
        images = []
        for img in img_elements:
            src = await img.get_attribute("src")
            if src:
                images.append(src)
        product.images = images if images else None
        
        # Extract breadcrumbs
        breadcrumb_elements = await page.query_selector_all('[itemprop="itemListElement"]')
        breadcrumbs = []
        for elem in breadcrumb_elements:
            name_elem = await elem.query_selector('[itemprop="name"]')
            if name_elem:
                breadcrumbs.append(await name_elem.inner_text())
        product.category_breadcrumbs = breadcrumbs if breadcrumbs else None
        
        return product
