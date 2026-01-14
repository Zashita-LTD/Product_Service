"""
Demo Parser.

A test parser that generates demo products without scraping real sites.
Useful for testing the ingestion pipeline.
"""

from typing import List, Optional, AsyncGenerator
from playwright.async_api import Page
import random

from parser_service.internal.parsers.base import BaseParser
from parser_service.internal.models.product import RawProduct


# Demo product data for testing
DEMO_PRODUCTS = [
    {
        "name": "Провод ПВС 3x1.5 мм² белый 50м",
        "brand": "Электрокабель",
        "category": ["Электротовары", "Кабели и провода"],
        "price": 2450.00,
        "images": ["https://placehold.co/400x400/blue/white?text=PVS+3x1.5"],
        "attributes": [
            {"name": "Сечение", "value": "3x1.5", "unit": "мм²"},
            {"name": "Длина", "value": "50", "unit": "м"},
            {"name": "Цвет", "value": "белый"},
        ]
    },
    {
        "name": "Автомат IEK ВА47-29 1P 16A C",
        "brand": "IEK",
        "category": ["Электротовары", "Автоматические выключатели"],
        "price": 185.00,
        "images": ["https://placehold.co/400x400/gray/white?text=IEK+16A"],
        "attributes": [
            {"name": "Ток", "value": "16", "unit": "А"},
            {"name": "Полюса", "value": "1P"},
            {"name": "Характеристика", "value": "C"},
        ]
    },
    {
        "name": "Розетка Schneider Electric Sedna с заземлением белая",
        "brand": "Schneider Electric",
        "category": ["Электротовары", "Розетки и выключатели"],
        "price": 289.00,
        "images": ["https://placehold.co/400x400/green/white?text=Sedna"],
        "attributes": [
            {"name": "Цвет", "value": "белый"},
            {"name": "Заземление", "value": "да"},
            {"name": "Серия", "value": "Sedna"},
        ]
    },
    {
        "name": "Лампа светодиодная Gauss LED A60 12W E27 4100K",
        "brand": "Gauss",
        "category": ["Освещение", "Лампочки"],
        "price": 145.00,
        "images": ["https://placehold.co/400x400/yellow/black?text=Gauss+12W"],
        "attributes": [
            {"name": "Мощность", "value": "12", "unit": "Вт"},
            {"name": "Цоколь", "value": "E27"},
            {"name": "Цветовая температура", "value": "4100", "unit": "K"},
        ]
    },
    {
        "name": "Кабель ВВГнг-LS 3x2.5 мм² 100м",
        "brand": "Конкорд",
        "category": ["Электротовары", "Кабели и провода"],
        "price": 8900.00,
        "images": ["https://placehold.co/400x400/orange/white?text=VVG+3x2.5"],
        "attributes": [
            {"name": "Сечение", "value": "3x2.5", "unit": "мм²"},
            {"name": "Длина", "value": "100", "unit": "м"},
            {"name": "Тип", "value": "ВВГнг-LS"},
        ]
    },
    {
        "name": "Удлинитель 4 розетки 3м с выключателем",
        "brand": "ЭРА",
        "category": ["Электротовары", "Удлинители"],
        "price": 450.00,
        "images": ["https://placehold.co/400x400/red/white?text=ERA+4x3m"],
        "attributes": [
            {"name": "Количество розеток", "value": "4"},
            {"name": "Длина шнура", "value": "3", "unit": "м"},
            {"name": "Выключатель", "value": "да"},
        ]
    },
    {
        "name": "Труба гофрированная ПНД d16 мм 100м серая",
        "brand": "DKC",
        "category": ["Электротовары", "Гофротруба"],
        "price": 1250.00,
        "images": ["https://placehold.co/400x400/purple/white?text=DKC+16mm"],
        "attributes": [
            {"name": "Диаметр", "value": "16", "unit": "мм"},
            {"name": "Длина", "value": "100", "unit": "м"},
            {"name": "Материал", "value": "ПНД"},
        ]
    },
    {
        "name": "Клеммы WAGO 222-412 2-проводные",
        "brand": "WAGO",
        "category": ["Электротовары", "Клеммы"],
        "price": 35.00,
        "images": ["https://placehold.co/400x400/teal/white?text=WAGO+222"],
        "attributes": [
            {"name": "Количество проводов", "value": "2"},
            {"name": "Сечение", "value": "0.08-4", "unit": "мм²"},
            {"name": "Серия", "value": "222"},
        ]
    },
    {
        "name": "Щит распределительный ЩРН-12 IP41",
        "brand": "TDM",
        "category": ["Электротовары", "Щиты и боксы"],
        "price": 890.00,
        "images": ["https://placehold.co/400x400/navy/white?text=TDM+12"],
        "attributes": [
            {"name": "Модулей", "value": "12"},
            {"name": "IP", "value": "41"},
            {"name": "Монтаж", "value": "навесной"},
        ]
    },
    {
        "name": "Изолента ПВХ 19мм x 20м черная",
        "brand": "3M",
        "category": ["Электротовары", "Изоляционные материалы"],
        "price": 95.00,
        "images": ["https://placehold.co/400x400/black/white?text=3M+Tape"],
        "attributes": [
            {"name": "Ширина", "value": "19", "unit": "мм"},
            {"name": "Длина", "value": "20", "unit": "м"},
            {"name": "Цвет", "value": "черный"},
        ]
    },
]


class DemoParser(BaseParser):
    """Demo parser that generates test products."""

    def __init__(self, base_url: str = "https://demo.local"):
        """Initialize Demo parser."""
        self.base_url = base_url
        self._product_index = 0

    @property
    def name(self) -> str:
        return "demo.local"

    async def get_category_urls(self, page: Page) -> List[str]:
        """Return demo category URLs."""
        return [
            f"{self.base_url}/category/elektrotovary",
            f"{self.base_url}/category/osveschenie",
        ]

    async def get_product_urls(self, page: Page, category_url: str) -> AsyncGenerator[str, None]:
        """Generate demo product URLs."""
        # Generate 5 product URLs per category
        for i in range(5):
            yield f"{self.base_url}/product/{self._product_index + i}"

    async def parse_product(self, page: Page, url: str) -> Optional[RawProduct]:
        """Return a demo product."""
        if self._product_index >= len(DEMO_PRODUCTS):
            self._product_index = 0
        
        data = DEMO_PRODUCTS[self._product_index]
        self._product_index += 1
        
        product = RawProduct(
            source_url=url,
            source_name="demo.local",
            name_original=data["name"],
            brand=data.get("brand"),
            category_breadcrumbs=data.get("category"),
            attributes=data.get("attributes"),
            images=data.get("images"),
            price_amount=data.get("price"),
            price_currency="RUB",
            availability="in_stock",
        )
        
        return product
