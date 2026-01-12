"""
Parsers for construction material stores.

This module exports all available parsers.
"""
from parser_service.internal.parsers.base import BaseParser
from parser_service.internal.parsers.petrovich import PetrovichParser
from parser_service.internal.parsers.leroymerlin import LeroyMerlinParser
from parser_service.internal.parsers.sdvor import SdvorParser
from parser_service.internal.parsers.obi import ObiParser

__all__ = [
    "BaseParser",
    "PetrovichParser",
    "LeroyMerlinParser",
    "SdvorParser",
    "ObiParser",
]
