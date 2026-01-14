"""
CRM Domain Models.

Domain entities for CRM module: Manufacturers, Suppliers, Persons, Career History.
Following DDD principles - rich domain models with business logic.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID, uuid4
from enum import Enum

from .errors import DomainValidationError


# ============================================================================
# ENUMS
# ============================================================================

class PartnerStatus(str, Enum):
    """Partner relationship status with manufacturer."""
    NONE = "None"
    DEALER = "Dealer"
    DISTRIBUTOR = "Distributor"
    OFFICIAL = "Official"


class SupplierStatus(str, Enum):
    """Supplier operational status."""
    ACTIVE = "Active"
    INACTIVE = "Inactive"
    BLACKLISTED = "Blacklisted"


class CompanyType(str, Enum):
    """Type of company for career history."""
    SUPPLIER = "Supplier"
    MANUFACTURER = "Manufacturer"


class InteractionType(str, Enum):
    """Type of interaction with contact."""
    CALL = "Call"
    EMAIL = "Email"
    MEETING = "Meeting"
    MESSAGE = "Message"
    GIFT = "Gift"


class InteractionDirection(str, Enum):
    """Direction of interaction."""
    INBOUND = "Inbound"
    OUTBOUND = "Outbound"


# ============================================================================
# MANUFACTURER (Производитель)
# ============================================================================

@dataclass
class Manufacturer:
    """
    Manufacturer (Brand) entity.
    
    Examples: Кнауф, Волма, Bosch, Makita
    Stores info about product manufacturers and our relationship with them.
    """
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    name_normalized: Optional[str] = None
    description: Optional[str] = None
    country: Optional[str] = None
    website: Optional[str] = None
    
    # Partner relationship
    partner_status: PartnerStatus = PartnerStatus.NONE
    discount_percent: Decimal = Decimal("0.0")
    contract_number: Optional[str] = None
    contract_valid_until: Optional[date] = None
    
    # Contact info
    support_email: Optional[str] = None
    support_phone: Optional[str] = None
    
    # Metadata
    catalogs_url: Optional[str] = None
    notes: Optional[str] = None
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self) -> None:
        self._validate()
        if not self.name_normalized and self.name:
            self.name_normalized = self._normalize_name(self.name)
    
    def _validate(self) -> None:
        if not self.name:
            raise DomainValidationError("Manufacturer name is required")
        if self.discount_percent < 0 or self.discount_percent > 100:
            raise DomainValidationError("Discount must be between 0 and 100")
    
    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize name for search: lowercase, no special chars."""
        import re
        normalized = name.lower().strip()
        normalized = re.sub(r'[^\w\s]', '', normalized)
        return normalized
    
    def set_partner_status(self, status: PartnerStatus, discount: Decimal) -> None:
        """Update partner status and discount."""
        self.partner_status = status
        self.discount_percent = discount
        self.updated_at = datetime.utcnow()
    
    def is_contract_valid(self) -> bool:
        """Check if partnership contract is still valid."""
        if not self.contract_valid_until:
            return False
        return self.contract_valid_until >= date.today()
    
    def calculate_net_price(self, gross_price: Decimal) -> Decimal:
        """Calculate net price after our discount."""
        discount_multiplier = 1 - (self.discount_percent / 100)
        return gross_price * discount_multiplier


# ============================================================================
# SUPPLIER (Поставщик)
# ============================================================================

@dataclass
class Supplier:
    """
    Supplier (Dealer) entity.
    
    Examples: Петрович, СтройДвор, Металл-Сервис, ИП Иванов
    Companies we buy products from.
    """
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    legal_name: Optional[str] = None
    inn: Optional[str] = None
    kpp: Optional[str] = None
    ogrn: Optional[str] = None
    
    # Contact
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    
    # Ratings (0.00 - 5.00)
    rating: Decimal = Decimal("0.0")
    reliability_score: Decimal = Decimal("0.0")
    price_score: Decimal = Decimal("0.0")
    total_orders: int = 0
    successful_orders: int = 0
    
    # Terms
    payment_terms: Optional[str] = None  # 'Prepay', 'Net30', 'Net60'
    delivery_days: Optional[int] = None
    min_order_amount: Optional[Decimal] = None
    
    # Status
    status: SupplierStatus = SupplierStatus.ACTIVE
    blacklist_reason: Optional[str] = None
    
    notes: Optional[str] = None
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self) -> None:
        self._validate()
    
    def _validate(self) -> None:
        if not self.name:
            raise DomainValidationError("Supplier name is required")
        if self.inn and len(self.inn) not in [10, 12]:
            raise DomainValidationError("INN must be 10 or 12 digits")
    
    def record_order(self, successful: bool) -> None:
        """Record order outcome and update statistics."""
        self.total_orders += 1
        if successful:
            self.successful_orders += 1
        self._recalculate_rating()
        self.updated_at = datetime.utcnow()
    
    def _recalculate_rating(self) -> None:
        """Recalculate reliability score based on order history."""
        if self.total_orders > 0:
            success_rate = self.successful_orders / self.total_orders
            self.reliability_score = Decimal(str(round(success_rate * 5, 2)))
    
    def blacklist(self, reason: str) -> None:
        """Add supplier to blacklist."""
        self.status = SupplierStatus.BLACKLISTED
        self.blacklist_reason = reason
        self.updated_at = datetime.utcnow()
    
    def activate(self) -> None:
        """Activate supplier."""
        self.status = SupplierStatus.ACTIVE
        self.blacklist_reason = None
        self.updated_at = datetime.utcnow()
    
    @property
    def success_rate(self) -> float:
        """Calculate order success rate."""
        if self.total_orders == 0:
            return 0.0
        return self.successful_orders / self.total_orders


# ============================================================================
# PERSON (Контакт/Менеджер)
# ============================================================================

@dataclass
class Person:
    """
    Person (Contact) entity.
    
    Managers and contacts we work with. The most valuable CRM asset!
    Key feature: person is NOT permanently tied to a company - they can switch jobs.
    """
    id: UUID = field(default_factory=uuid4)
    full_name: str = ""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    
    # Contacts
    phone: Optional[str] = None
    phone_mobile: Optional[str] = None
    email: Optional[str] = None
    telegram_id: Optional[str] = None
    whatsapp: Optional[str] = None
    
    # CRM data
    birth_date: Optional[date] = None
    gender: Optional[str] = None
    
    # Personal notes (confidential!)
    notes: Optional[str] = None  # "Loves fishing, prefers Hennessy cognac"
    interests: Optional[str] = None
    preferred_contact_method: Optional[str] = None
    
    # Professional
    specialization: Optional[str] = None
    
    # Status
    is_active: bool = True
    last_contact_date: Optional[date] = None
    
    # Career history (loaded separately)
    career_history: List["CareerRecord"] = field(default_factory=list)
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self) -> None:
        self._validate()
        self._parse_full_name()
    
    def _validate(self) -> None:
        if not self.full_name:
            raise DomainValidationError("Person full_name is required")
    
    def _parse_full_name(self) -> None:
        """Parse full name into components if not provided."""
        if self.full_name and not self.last_name:
            parts = self.full_name.split()
            if len(parts) >= 1:
                self.last_name = parts[0]
            if len(parts) >= 2:
                self.first_name = parts[1]
            if len(parts) >= 3:
                self.middle_name = parts[2]
    
    def change_job(
        self,
        company_id: UUID,
        company_type: CompanyType,
        role: str,
        start_date: Optional[date] = None,
        work_phone: Optional[str] = None,
        work_email: Optional[str] = None,
    ) -> "CareerRecord":
        """
        Record job change. Creates new career record and closes previous.
        
        Returns:
            New CareerRecord for the new position.
        """
        # Close current position
        for record in self.career_history:
            if record.is_current:
                record.end_job(start_date or date.today())
        
        # Create new position
        new_record = CareerRecord(
            person_id=self.id,
            company_id=company_id,
            company_type=company_type,
            role=role,
            start_date=start_date or date.today(),
            is_current=True,
            work_phone=work_phone,
            work_email=work_email,
        )
        self.career_history.append(new_record)
        self.updated_at = datetime.utcnow()
        
        return new_record
    
    @property
    def current_job(self) -> Optional["CareerRecord"]:
        """Get current job position."""
        for record in self.career_history:
            if record.is_current:
                return record
        return None
    
    @property
    def days_until_birthday(self) -> Optional[int]:
        """Calculate days until next birthday."""
        if not self.birth_date:
            return None
        
        today = date.today()
        this_year_birthday = self.birth_date.replace(year=today.year)
        
        if this_year_birthday < today:
            next_birthday = this_year_birthday.replace(year=today.year + 1)
        else:
            next_birthday = this_year_birthday
        
        return (next_birthday - today).days
    
    @property
    def age(self) -> Optional[int]:
        """Calculate current age."""
        if not self.birth_date:
            return None
        
        today = date.today()
        age = today.year - self.birth_date.year
        
        # Adjust if birthday hasn't occurred yet this year
        if (today.month, today.day) < (self.birth_date.month, self.birth_date.day):
            age -= 1
        
        return age
    
    def record_contact(self) -> None:
        """Record that we contacted this person."""
        self.last_contact_date = date.today()
        self.updated_at = datetime.utcnow()


# ============================================================================
# CAREER RECORD (Запись о карьере)
# ============================================================================

@dataclass
class CareerRecord:
    """
    Career history record.
    
    Tracks where a person worked/works.
    Allows tracking job changes between companies.
    """
    id: UUID = field(default_factory=uuid4)
    person_id: UUID = field(default_factory=uuid4)
    company_id: UUID = field(default_factory=uuid4)
    company_type: CompanyType = CompanyType.SUPPLIER
    
    role: Optional[str] = None
    department: Optional[str] = None
    
    start_date: date = field(default_factory=date.today)
    end_date: Optional[date] = None
    is_current: bool = False
    
    work_phone: Optional[str] = None
    work_email: Optional[str] = None
    
    notes: Optional[str] = None
    
    # Denormalized company name (for display)
    company_name: Optional[str] = None
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def end_job(self, end_date: Optional[date] = None) -> None:
        """Mark this job as ended."""
        self.is_current = False
        self.end_date = end_date or date.today()
        self.updated_at = datetime.utcnow()
    
    @property
    def duration_months(self) -> int:
        """Calculate duration in months."""
        end = self.end_date or date.today()
        return (end.year - self.start_date.year) * 12 + (end.month - self.start_date.month)


# ============================================================================
# INTERACTION (Взаимодействие)
# ============================================================================

@dataclass
class Interaction:
    """
    Interaction record with a contact.
    
    Logs all communications: calls, emails, meetings, gifts.
    """
    id: UUID = field(default_factory=uuid4)
    person_id: UUID = field(default_factory=uuid4)
    
    interaction_type: InteractionType = InteractionType.CALL
    direction: InteractionDirection = InteractionDirection.OUTBOUND
    
    subject: Optional[str] = None
    content: Optional[str] = None
    
    outcome: Optional[str] = None  # 'Success', 'No Answer', 'Callback', 'Deal'
    next_action: Optional[str] = None
    next_action_date: Optional[date] = None
    
    deal_id: Optional[UUID] = None
    created_by: Optional[str] = None
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self) -> None:
        self._validate()
    
    def _validate(self) -> None:
        if not self.person_id:
            raise DomainValidationError("person_id is required for interaction")


# ============================================================================
# SUPPLIER-MANUFACTURER LINK
# ============================================================================

@dataclass
class SupplierManufacturer:
    """
    Link between supplier and manufacturer.
    
    Tracks which brands a supplier sells and on what terms.
    """
    id: UUID = field(default_factory=uuid4)
    supplier_id: UUID = field(default_factory=uuid4)
    manufacturer_id: UUID = field(default_factory=uuid4)
    
    is_official_dealer: bool = False
    discount_percent: Decimal = Decimal("0.0")
    
    created_at: datetime = field(default_factory=datetime.utcnow)
