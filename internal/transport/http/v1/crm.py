"""
CRM API Handlers.

REST API endpoints for CRM module: Manufacturers, Suppliers, Persons.
"""

from datetime import date
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from internal.domain.crm import (
    Manufacturer, Supplier, Person, CareerRecord, Interaction,
    PartnerStatus, SupplierStatus, CompanyType,
    InteractionType, InteractionDirection
)
from internal.infrastructure.postgres.crm_repository import CRMRepository
from pkg.logger.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/crm", tags=["crm"])


# ============================================================================
# DTOs (Request/Response Models)
# ============================================================================

# --- Manufacturer DTOs ---

class ManufacturerCreate(BaseModel):
    """Create manufacturer request."""
    name: str = Field(..., min_length=1, max_length=255, example="Кнауф")
    description: Optional[str] = Field(None, example="Производитель сухих строительных смесей")
    country: Optional[str] = Field(None, example="Германия")
    website: Optional[str] = Field(None, example="https://knauf.ru")
    partner_status: str = Field("None", example="Dealer")
    discount_percent: float = Field(0.0, ge=0, le=100, example=15.0)
    contract_number: Optional[str] = None
    contract_valid_until: Optional[date] = None
    support_email: Optional[str] = None
    support_phone: Optional[str] = None
    catalogs_url: Optional[str] = None
    notes: Optional[str] = None


class ManufacturerResponse(BaseModel):
    """Manufacturer response."""
    id: UUID
    name: str
    name_normalized: Optional[str]
    description: Optional[str]
    country: Optional[str]
    website: Optional[str]
    partner_status: str
    discount_percent: float
    contract_number: Optional[str]
    contract_valid_until: Optional[date]
    support_email: Optional[str]
    support_phone: Optional[str]
    catalogs_url: Optional[str]
    notes: Optional[str]
    
    class Config:
        from_attributes = True


# --- Supplier DTOs ---

class SupplierCreate(BaseModel):
    """Create supplier request."""
    name: str = Field(..., min_length=1, max_length=255, example="Петрович")
    legal_name: Optional[str] = Field(None, example='ООО "Петрович"')
    inn: Optional[str] = Field(None, min_length=10, max_length=12, example="7810000000")
    kpp: Optional[str] = None
    ogrn: Optional[str] = None
    website: Optional[str] = Field(None, example="https://petrovich.ru")
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    payment_terms: Optional[str] = Field(None, example="Net30")
    delivery_days: Optional[int] = Field(None, ge=0)
    min_order_amount: Optional[float] = None
    notes: Optional[str] = None


class SupplierResponse(BaseModel):
    """Supplier response."""
    id: UUID
    name: str
    legal_name: Optional[str]
    inn: Optional[str]
    kpp: Optional[str]
    ogrn: Optional[str]
    website: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    rating: float
    reliability_score: float
    price_score: float
    total_orders: int
    successful_orders: int
    success_rate: float
    payment_terms: Optional[str]
    delivery_days: Optional[int]
    min_order_amount: Optional[float]
    status: str
    blacklist_reason: Optional[str]
    notes: Optional[str]
    
    class Config:
        from_attributes = True


# --- Person DTOs ---

class PersonCreate(BaseModel):
    """Create person request."""
    full_name: str = Field(..., min_length=1, max_length=255, example="Иванов Иван Иванович")
    phone: Optional[str] = Field(None, example="+7 999 123-45-67")
    phone_mobile: Optional[str] = None
    email: Optional[str] = Field(None, example="ivanov@example.com")
    telegram_id: Optional[str] = Field(None, example="@ivanov")
    whatsapp: Optional[str] = None
    birth_date: Optional[date] = Field(None, example="1985-03-15")
    gender: Optional[str] = Field(None, example="Male")
    notes: Optional[str] = Field(None, example="Любит рыбалку, коньяк Hennessy")
    interests: Optional[str] = None
    preferred_contact_method: Optional[str] = Field(None, example="Telegram")
    specialization: Optional[str] = Field(None, example="Сухие смеси")


class PersonResponse(BaseModel):
    """Person response."""
    id: UUID
    full_name: str
    first_name: Optional[str]
    last_name: Optional[str]
    middle_name: Optional[str]
    phone: Optional[str]
    phone_mobile: Optional[str]
    email: Optional[str]
    telegram_id: Optional[str]
    whatsapp: Optional[str]
    birth_date: Optional[date]
    gender: Optional[str]
    notes: Optional[str]
    interests: Optional[str]
    preferred_contact_method: Optional[str]
    specialization: Optional[str]
    is_active: bool
    last_contact_date: Optional[date]
    days_until_birthday: Optional[int]
    age: Optional[int]
    current_job: Optional[dict] = None
    
    class Config:
        from_attributes = True


# --- Career DTOs ---

class JobChangeRequest(BaseModel):
    """Job change request - person moves to new company."""
    company_id: UUID = Field(..., description="ID поставщика или производителя")
    company_type: str = Field(..., example="Supplier", description="'Supplier' или 'Manufacturer'")
    role: str = Field(..., example="Менеджер по продажам")
    department: Optional[str] = Field(None, example="Отдел продаж")
    start_date: Optional[date] = None
    work_phone: Optional[str] = None
    work_email: Optional[str] = None
    notes: Optional[str] = None


class CareerResponse(BaseModel):
    """Career record response."""
    id: UUID
    person_id: UUID
    company_id: UUID
    company_type: str
    company_name: Optional[str]
    role: Optional[str]
    department: Optional[str]
    start_date: date
    end_date: Optional[date]
    is_current: bool
    work_phone: Optional[str]
    work_email: Optional[str]
    duration_months: int
    
    class Config:
        from_attributes = True


# --- Interaction DTOs ---

class InteractionCreate(BaseModel):
    """Create interaction request."""
    person_id: UUID
    interaction_type: str = Field(..., example="Call")
    direction: str = Field("Outbound", example="Outbound")
    subject: Optional[str] = Field(None, example="Обсуждение условий поставки")
    content: Optional[str] = None
    outcome: Optional[str] = Field(None, example="Success")
    next_action: Optional[str] = Field(None, example="Отправить КП")
    next_action_date: Optional[date] = None
    created_by: Optional[str] = None


class InteractionResponse(BaseModel):
    """Interaction response."""
    id: UUID
    person_id: UUID
    interaction_type: str
    direction: str
    subject: Optional[str]
    content: Optional[str]
    outcome: Optional[str]
    next_action: Optional[str]
    next_action_date: Optional[date]
    created_by: Optional[str]
    created_at: str
    
    class Config:
        from_attributes = True


# --- Birthday DTO ---

class BirthdayResponse(BaseModel):
    """Upcoming birthday response."""
    id: UUID
    full_name: str
    birth_date: date
    phone: Optional[str]
    telegram_id: Optional[str]
    notes: Optional[str]
    role: Optional[str]
    company_name: Optional[str]
    days_until_birthday: int


# ============================================================================
# Dependency - Repository
# ============================================================================

# This will be injected by the main app
_crm_repo: Optional[CRMRepository] = None


def get_crm_repository() -> CRMRepository:
    """Get CRM repository instance."""
    if _crm_repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CRM repository not initialized"
        )
    return _crm_repo


def set_crm_repository(repo: CRMRepository) -> None:
    """Set CRM repository instance (called during app startup)."""
    global _crm_repo
    _crm_repo = repo


# ============================================================================
# MANUFACTURER ENDPOINTS
# ============================================================================

@router.post("/manufacturers", response_model=ManufacturerResponse, status_code=status.HTTP_201_CREATED)
async def create_manufacturer(
    data: ManufacturerCreate,
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Create a new manufacturer (brand)."""
    try:
        manufacturer = Manufacturer(
            name=data.name,
            description=data.description,
            country=data.country,
            website=data.website,
            partner_status=PartnerStatus(data.partner_status),
            discount_percent=Decimal(str(data.discount_percent)),
            contract_number=data.contract_number,
            contract_valid_until=data.contract_valid_until,
            support_email=data.support_email,
            support_phone=data.support_phone,
            catalogs_url=data.catalogs_url,
            notes=data.notes,
        )
        created = await repo.create_manufacturer(manufacturer)
        logger.info(f"Created manufacturer: {created.name}")
        return _manufacturer_to_response(created)
    except Exception as e:
        logger.error(f"Error creating manufacturer: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/manufacturers", response_model=List[ManufacturerResponse])
async def list_manufacturers(
    search: Optional[str] = Query(None, description="Search by name"),
    partner_status: Optional[str] = Query(None, description="Filter by partner status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    repo: CRMRepository = Depends(get_crm_repository)
):
    """List manufacturers with optional filters."""
    status_enum = PartnerStatus(partner_status) if partner_status else None
    manufacturers = await repo.find_manufacturers(
        search=search,
        partner_status=status_enum,
        limit=limit,
        offset=offset
    )
    return [_manufacturer_to_response(m) for m in manufacturers]


@router.get("/manufacturers/{id}", response_model=ManufacturerResponse)
async def get_manufacturer(
    id: UUID,
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Get manufacturer by ID."""
    manufacturer = await repo.get_manufacturer(id)
    if not manufacturer:
        raise HTTPException(status_code=404, detail="Manufacturer not found")
    return _manufacturer_to_response(manufacturer)


@router.get("/manufacturers/by-name/{name}", response_model=ManufacturerResponse)
async def get_manufacturer_by_name(
    name: str,
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Get manufacturer by name (normalized search)."""
    manufacturer = await repo.get_manufacturer_by_name(name)
    if not manufacturer:
        raise HTTPException(status_code=404, detail="Manufacturer not found")
    return _manufacturer_to_response(manufacturer)


def _manufacturer_to_response(m: Manufacturer) -> ManufacturerResponse:
    return ManufacturerResponse(
        id=m.id,
        name=m.name,
        name_normalized=m.name_normalized,
        description=m.description,
        country=m.country,
        website=m.website,
        partner_status=m.partner_status.value,
        discount_percent=float(m.discount_percent),
        contract_number=m.contract_number,
        contract_valid_until=m.contract_valid_until,
        support_email=m.support_email,
        support_phone=m.support_phone,
        catalogs_url=m.catalogs_url,
        notes=m.notes,
    )


# ============================================================================
# SUPPLIER ENDPOINTS
# ============================================================================

@router.post("/suppliers", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    data: SupplierCreate,
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Create a new supplier (dealer)."""
    try:
        supplier = Supplier(
            name=data.name,
            legal_name=data.legal_name,
            inn=data.inn,
            kpp=data.kpp,
            ogrn=data.ogrn,
            website=data.website,
            email=data.email,
            phone=data.phone,
            address=data.address,
            payment_terms=data.payment_terms,
            delivery_days=data.delivery_days,
            min_order_amount=Decimal(str(data.min_order_amount)) if data.min_order_amount else None,
            notes=data.notes,
        )
        created = await repo.create_supplier(supplier)
        logger.info(f"Created supplier: {created.name}")
        return _supplier_to_response(created)
    except Exception as e:
        logger.error(f"Error creating supplier: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/suppliers", response_model=List[SupplierResponse])
async def list_suppliers(
    search: Optional[str] = Query(None, description="Search by name or INN"),
    status: Optional[str] = Query(None, description="Filter by status"),
    min_rating: Optional[float] = Query(None, ge=0, le=5),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    repo: CRMRepository = Depends(get_crm_repository)
):
    """List suppliers with optional filters."""
    status_enum = SupplierStatus(status) if status else None
    suppliers = await repo.find_suppliers(
        search=search,
        status=status_enum,
        min_rating=min_rating,
        limit=limit,
        offset=offset
    )
    return [_supplier_to_response(s) for s in suppliers]


@router.get("/suppliers/{id}", response_model=SupplierResponse)
async def get_supplier(
    id: UUID,
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Get supplier by ID."""
    supplier = await repo.get_supplier(id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return _supplier_to_response(supplier)


@router.post("/suppliers/{id}/blacklist")
async def blacklist_supplier(
    id: UUID,
    reason: str = Query(..., description="Reason for blacklisting"),
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Add supplier to blacklist."""
    supplier = await repo.get_supplier(id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    supplier.blacklist(reason)
    await repo.update_supplier(supplier)
    logger.warning(f"Blacklisted supplier {supplier.name}: {reason}")
    return {"status": "blacklisted", "supplier_id": str(id)}


def _supplier_to_response(s: Supplier) -> SupplierResponse:
    return SupplierResponse(
        id=s.id,
        name=s.name,
        legal_name=s.legal_name,
        inn=s.inn,
        kpp=s.kpp,
        ogrn=s.ogrn,
        website=s.website,
        email=s.email,
        phone=s.phone,
        address=s.address,
        rating=float(s.rating),
        reliability_score=float(s.reliability_score),
        price_score=float(s.price_score),
        total_orders=s.total_orders,
        successful_orders=s.successful_orders,
        success_rate=s.success_rate,
        payment_terms=s.payment_terms,
        delivery_days=s.delivery_days,
        min_order_amount=float(s.min_order_amount) if s.min_order_amount else None,
        status=s.status.value,
        blacklist_reason=s.blacklist_reason,
        notes=s.notes,
    )


# ============================================================================
# PERSON ENDPOINTS
# ============================================================================

@router.post("/persons", response_model=PersonResponse, status_code=status.HTTP_201_CREATED)
async def create_person(
    data: PersonCreate,
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Create a new person (contact)."""
    try:
        person = Person(
            full_name=data.full_name,
            phone=data.phone,
            phone_mobile=data.phone_mobile,
            email=data.email,
            telegram_id=data.telegram_id,
            whatsapp=data.whatsapp,
            birth_date=data.birth_date,
            gender=data.gender,
            notes=data.notes,
            interests=data.interests,
            preferred_contact_method=data.preferred_contact_method,
            specialization=data.specialization,
        )
        created = await repo.create_person(person)
        logger.info(f"Created person: {created.full_name}")
        return _person_to_response(created)
    except Exception as e:
        logger.error(f"Error creating person: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/persons", response_model=List[PersonResponse])
async def list_persons(
    search: Optional[str] = Query(None, description="Search by name, phone, email"),
    company_id: Optional[UUID] = Query(None, description="Filter by current company"),
    is_active: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    repo: CRMRepository = Depends(get_crm_repository)
):
    """List persons with optional filters."""
    persons = await repo.find_persons(
        search=search,
        company_id=company_id,
        is_active=is_active,
        limit=limit,
        offset=offset
    )
    return [_person_to_response(p) for p in persons]


@router.get("/persons/{id}", response_model=PersonResponse)
async def get_person(
    id: UUID,
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Get person by ID with career history."""
    person = await repo.get_person(id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    return _person_to_response(person)


@router.post("/persons/{id}/job", response_model=CareerResponse)
async def change_person_job(
    id: UUID,
    data: JobChangeRequest,
    repo: CRMRepository = Depends(get_crm_repository)
):
    """
    Record job change for a person.
    
    Previous job (if any) will be automatically closed.
    """
    person = await repo.get_person(id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    try:
        new_record = person.change_job(
            company_id=data.company_id,
            company_type=CompanyType(data.company_type),
            role=data.role,
            start_date=data.start_date,
            work_phone=data.work_phone,
            work_email=data.work_email,
        )
        new_record.department = data.department
        new_record.notes = data.notes
        
        # Save to DB
        saved_record = await repo.add_career_record(new_record)
        await repo.update_person(person)
        
        logger.info(f"Person {person.full_name} changed job to {data.company_type}/{data.role}")
        return _career_to_response(saved_record)
    except Exception as e:
        logger.error(f"Error changing job: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/persons/{id}/career", response_model=List[CareerResponse])
async def get_person_career(
    id: UUID,
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Get person's career history."""
    person = await repo.get_person(id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    return [_career_to_response(c) for c in person.career_history]


@router.get("/companies/{company_id}/managers", response_model=List[PersonResponse])
async def get_company_managers(
    company_id: UUID,
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Get people currently working at a company."""
    persons = await repo.find_active_managers(company_id)
    return [_person_to_response(p) for p in persons]


def _person_to_response(p: Person) -> PersonResponse:
    current = p.current_job
    return PersonResponse(
        id=p.id,
        full_name=p.full_name,
        first_name=p.first_name,
        last_name=p.last_name,
        middle_name=p.middle_name,
        phone=p.phone,
        phone_mobile=p.phone_mobile,
        email=p.email,
        telegram_id=p.telegram_id,
        whatsapp=p.whatsapp,
        birth_date=p.birth_date,
        gender=p.gender,
        notes=p.notes,
        interests=p.interests,
        preferred_contact_method=p.preferred_contact_method,
        specialization=p.specialization,
        is_active=p.is_active,
        last_contact_date=p.last_contact_date,
        days_until_birthday=p.days_until_birthday,
        age=p.age,
        current_job={
            "company_id": str(current.company_id),
            "company_type": current.company_type.value,
            "company_name": current.company_name,
            "role": current.role,
        } if current else None,
    )


def _career_to_response(c: CareerRecord) -> CareerResponse:
    return CareerResponse(
        id=c.id,
        person_id=c.person_id,
        company_id=c.company_id,
        company_type=c.company_type.value,
        company_name=c.company_name,
        role=c.role,
        department=c.department,
        start_date=c.start_date,
        end_date=c.end_date,
        is_current=c.is_current,
        work_phone=c.work_phone,
        work_email=c.work_email,
        duration_months=c.duration_months,
    )


# ============================================================================
# BIRTHDAY ENDPOINTS
# ============================================================================

@router.get("/birthdays", response_model=List[BirthdayResponse])
async def get_upcoming_birthdays(
    days: int = Query(7, ge=0, le=365, description="Days ahead to check"),
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Get contacts with upcoming birthdays."""
    birthdays = await repo.get_upcoming_birthdays(days)
    return [BirthdayResponse(**b) for b in birthdays]


@router.get("/birthdays/today", response_model=List[BirthdayResponse])
async def get_birthdays_today(
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Get contacts with birthdays today."""
    birthdays = await repo.get_birthdays_today()
    return [BirthdayResponse(**b) for b in birthdays]


@router.get("/birthdays/week", response_model=List[BirthdayResponse])
async def get_birthdays_this_week(
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Get contacts with birthdays this week."""
    birthdays = await repo.get_birthdays_this_week()
    return [BirthdayResponse(**b) for b in birthdays]


# ============================================================================
# INTERACTION ENDPOINTS
# ============================================================================

@router.post("/interactions", response_model=InteractionResponse, status_code=status.HTTP_201_CREATED)
async def log_interaction(
    data: InteractionCreate,
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Log an interaction with a contact."""
    try:
        interaction = Interaction(
            person_id=data.person_id,
            interaction_type=InteractionType(data.interaction_type),
            direction=InteractionDirection(data.direction),
            subject=data.subject,
            content=data.content,
            outcome=data.outcome,
            next_action=data.next_action,
            next_action_date=data.next_action_date,
            created_by=data.created_by,
        )
        created = await repo.log_interaction(interaction)
        logger.info(f"Logged {data.interaction_type} with person {data.person_id}")
        return _interaction_to_response(created)
    except Exception as e:
        logger.error(f"Error logging interaction: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/persons/{id}/interactions", response_model=List[InteractionResponse])
async def get_person_interactions(
    id: UUID,
    limit: int = Query(50, ge=1, le=100),
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Get interaction history for a person."""
    interactions = await repo.get_person_interactions(id, limit)
    return [_interaction_to_response(i) for i in interactions]


@router.get("/actions/pending")
async def get_pending_actions(
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Get interactions with pending next actions (reminders)."""
    actions = await repo.get_pending_actions()
    return actions


def _interaction_to_response(i: Interaction) -> InteractionResponse:
    return InteractionResponse(
        id=i.id,
        person_id=i.person_id,
        interaction_type=i.interaction_type.value,
        direction=i.direction.value,
        subject=i.subject,
        content=i.content,
        outcome=i.outcome,
        next_action=i.next_action,
        next_action_date=i.next_action_date,
        created_by=i.created_by,
        created_at=i.created_at.isoformat(),
    )


# ============================================================================
# SUPPLIER-MANUFACTURER LINKS
# ============================================================================

@router.post("/suppliers/{supplier_id}/manufacturers/{manufacturer_id}")
async def link_supplier_to_manufacturer(
    supplier_id: UUID,
    manufacturer_id: UUID,
    is_official: bool = Query(False),
    discount: float = Query(0.0, ge=0, le=100),
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Link supplier to manufacturer (supplier sells this brand)."""
    link = await repo.link_supplier_manufacturer(
        supplier_id=supplier_id,
        manufacturer_id=manufacturer_id,
        is_official=is_official,
        discount=Decimal(str(discount))
    )
    return {
        "status": "linked",
        "supplier_id": str(supplier_id),
        "manufacturer_id": str(manufacturer_id),
        "is_official_dealer": link.is_official_dealer,
    }


@router.get("/suppliers/{id}/manufacturers", response_model=List[ManufacturerResponse])
async def get_supplier_manufacturers(
    id: UUID,
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Get manufacturers that a supplier sells."""
    manufacturers = await repo.get_supplier_manufacturers(id)
    return [_manufacturer_to_response(m) for m in manufacturers]


@router.get("/manufacturers/{id}/suppliers", response_model=List[SupplierResponse])
async def get_manufacturer_suppliers(
    id: UUID,
    repo: CRMRepository = Depends(get_crm_repository)
):
    """Get suppliers that sell a manufacturer's products."""
    suppliers = await repo.get_manufacturer_suppliers(id)
    return [_supplier_to_response(s) for s in suppliers]
