"""
CRM Repository.

PostgreSQL repository for CRM entities: Manufacturers, Suppliers, Persons.
"""
import asyncpg
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from ...domain.crm import (
    Manufacturer, Supplier, Person, CareerRecord, Interaction,
    PartnerStatus, SupplierStatus, CompanyType,
    InteractionType, InteractionDirection, SupplierManufacturer
)


class CRMRepository:
    """Repository for CRM operations."""
    
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool
    
    # ========================================================================
    # MANUFACTURERS
    # ========================================================================
    
    async def create_manufacturer(self, manufacturer: Manufacturer) -> Manufacturer:
        """Create a new manufacturer."""
        query = """
            INSERT INTO manufacturers (
                id, name, name_normalized, description, country, website,
                partner_status, discount_percent, contract_number, contract_valid_until,
                support_email, support_phone, catalogs_url, notes
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                manufacturer.id, manufacturer.name, manufacturer.name_normalized,
                manufacturer.description, manufacturer.country, manufacturer.website,
                manufacturer.partner_status.value, manufacturer.discount_percent,
                manufacturer.contract_number, manufacturer.contract_valid_until,
                manufacturer.support_email, manufacturer.support_phone,
                manufacturer.catalogs_url, manufacturer.notes
            )
        return self._row_to_manufacturer(row)
    
    async def get_manufacturer(self, id: UUID) -> Optional[Manufacturer]:
        """Get manufacturer by ID."""
        query = "SELECT * FROM manufacturers WHERE id = $1"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, id)
        return self._row_to_manufacturer(row) if row else None
    
    async def get_manufacturer_by_name(self, name: str) -> Optional[Manufacturer]:
        """Get manufacturer by name (normalized search)."""
        import re
        normalized = re.sub(r'[^\w\s]', '', name.lower().strip())
        query = "SELECT * FROM manufacturers WHERE name_normalized = $1"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, normalized)
        return self._row_to_manufacturer(row) if row else None
    
    async def find_manufacturers(
        self,
        search: Optional[str] = None,
        partner_status: Optional[PartnerStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Manufacturer]:
        """Find manufacturers with filters."""
        conditions = []
        params = []
        param_idx = 1
        
        if search:
            conditions.append(f"(name ILIKE ${param_idx} OR name_normalized ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1
        
        if partner_status:
            conditions.append(f"partner_status = ${param_idx}")
            params.append(partner_status.value)
            param_idx += 1
        
        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        
        query = f"""
            SELECT * FROM manufacturers
            WHERE {where_clause}
            ORDER BY name
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [self._row_to_manufacturer(row) for row in rows]
    
    async def update_manufacturer(self, manufacturer: Manufacturer) -> Manufacturer:
        """Update manufacturer."""
        query = """
            UPDATE manufacturers SET
                name = $2, name_normalized = $3, description = $4, country = $5,
                website = $6, partner_status = $7, discount_percent = $8,
                contract_number = $9, contract_valid_until = $10,
                support_email = $11, support_phone = $12, catalogs_url = $13, notes = $14,
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                manufacturer.id, manufacturer.name, manufacturer.name_normalized,
                manufacturer.description, manufacturer.country, manufacturer.website,
                manufacturer.partner_status.value, manufacturer.discount_percent,
                manufacturer.contract_number, manufacturer.contract_valid_until,
                manufacturer.support_email, manufacturer.support_phone,
                manufacturer.catalogs_url, manufacturer.notes
            )
        return self._row_to_manufacturer(row)
    
    def _row_to_manufacturer(self, row: asyncpg.Record) -> Manufacturer:
        """Convert database row to Manufacturer domain object."""
        return Manufacturer(
            id=row['id'],
            name=row['name'],
            name_normalized=row['name_normalized'],
            description=row['description'],
            country=row['country'],
            website=row['website'],
            partner_status=PartnerStatus(row['partner_status']) if row['partner_status'] else PartnerStatus.NONE,
            discount_percent=Decimal(str(row['discount_percent'])) if row['discount_percent'] else Decimal("0"),
            contract_number=row['contract_number'],
            contract_valid_until=row['contract_valid_until'],
            support_email=row['support_email'],
            support_phone=row['support_phone'],
            catalogs_url=row['catalogs_url'],
            notes=row['notes'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )
    
    # ========================================================================
    # SUPPLIERS
    # ========================================================================
    
    async def create_supplier(self, supplier: Supplier) -> Supplier:
        """Create a new supplier."""
        query = """
            INSERT INTO suppliers (
                id, name, legal_name, inn, kpp, ogrn,
                website, email, phone, address,
                rating, reliability_score, price_score,
                total_orders, successful_orders,
                payment_terms, delivery_days, min_order_amount,
                status, blacklist_reason, notes
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21)
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                supplier.id, supplier.name, supplier.legal_name, supplier.inn, supplier.kpp, supplier.ogrn,
                supplier.website, supplier.email, supplier.phone, supplier.address,
                supplier.rating, supplier.reliability_score, supplier.price_score,
                supplier.total_orders, supplier.successful_orders,
                supplier.payment_terms, supplier.delivery_days, supplier.min_order_amount,
                supplier.status.value, supplier.blacklist_reason, supplier.notes
            )
        return self._row_to_supplier(row)
    
    async def get_supplier(self, id: UUID) -> Optional[Supplier]:
        """Get supplier by ID."""
        query = "SELECT * FROM suppliers WHERE id = $1"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, id)
        return self._row_to_supplier(row) if row else None
    
    async def get_supplier_by_inn(self, inn: str) -> Optional[Supplier]:
        """Get supplier by INN."""
        query = "SELECT * FROM suppliers WHERE inn = $1"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, inn)
        return self._row_to_supplier(row) if row else None
    
    async def find_suppliers(
        self,
        search: Optional[str] = None,
        status: Optional[SupplierStatus] = None,
        min_rating: Optional[float] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Supplier]:
        """Find suppliers with filters."""
        conditions = []
        params = []
        param_idx = 1
        
        if search:
            conditions.append(f"(name ILIKE ${param_idx} OR legal_name ILIKE ${param_idx} OR inn ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1
        
        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1
        
        if min_rating is not None:
            conditions.append(f"rating >= ${param_idx}")
            params.append(min_rating)
            param_idx += 1
        
        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        
        query = f"""
            SELECT * FROM suppliers
            WHERE {where_clause}
            ORDER BY rating DESC, name
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [self._row_to_supplier(row) for row in rows]
    
    async def update_supplier(self, supplier: Supplier) -> Supplier:
        """Update supplier."""
        query = """
            UPDATE suppliers SET
                name = $2, legal_name = $3, inn = $4, kpp = $5, ogrn = $6,
                website = $7, email = $8, phone = $9, address = $10,
                rating = $11, reliability_score = $12, price_score = $13,
                total_orders = $14, successful_orders = $15,
                payment_terms = $16, delivery_days = $17, min_order_amount = $18,
                status = $19, blacklist_reason = $20, notes = $21,
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                supplier.id, supplier.name, supplier.legal_name, supplier.inn, supplier.kpp, supplier.ogrn,
                supplier.website, supplier.email, supplier.phone, supplier.address,
                supplier.rating, supplier.reliability_score, supplier.price_score,
                supplier.total_orders, supplier.successful_orders,
                supplier.payment_terms, supplier.delivery_days, supplier.min_order_amount,
                supplier.status.value, supplier.blacklist_reason, supplier.notes
            )
        return self._row_to_supplier(row)
    
    def _row_to_supplier(self, row: asyncpg.Record) -> Supplier:
        """Convert database row to Supplier domain object."""
        return Supplier(
            id=row['id'],
            name=row['name'],
            legal_name=row['legal_name'],
            inn=row['inn'],
            kpp=row['kpp'],
            ogrn=row['ogrn'],
            website=row['website'],
            email=row['email'],
            phone=row['phone'],
            address=row['address'],
            rating=Decimal(str(row['rating'])) if row['rating'] else Decimal("0"),
            reliability_score=Decimal(str(row['reliability_score'])) if row['reliability_score'] else Decimal("0"),
            price_score=Decimal(str(row['price_score'])) if row['price_score'] else Decimal("0"),
            total_orders=row['total_orders'] or 0,
            successful_orders=row['successful_orders'] or 0,
            payment_terms=row['payment_terms'],
            delivery_days=row['delivery_days'],
            min_order_amount=Decimal(str(row['min_order_amount'])) if row['min_order_amount'] else None,
            status=SupplierStatus(row['status']) if row['status'] else SupplierStatus.ACTIVE,
            blacklist_reason=row['blacklist_reason'],
            notes=row['notes'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )
    
    # ========================================================================
    # PERSONS
    # ========================================================================
    
    async def create_person(self, person: Person) -> Person:
        """Create a new person."""
        query = """
            INSERT INTO persons (
                id, full_name, first_name, last_name, middle_name,
                phone, phone_mobile, email, telegram_id, whatsapp,
                birth_date, gender, notes, interests, preferred_contact_method,
                specialization, is_active, last_contact_date
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                person.id, person.full_name, person.first_name, person.last_name, person.middle_name,
                person.phone, person.phone_mobile, person.email, person.telegram_id, person.whatsapp,
                person.birth_date, person.gender, person.notes, person.interests, person.preferred_contact_method,
                person.specialization, person.is_active, person.last_contact_date
            )
        return self._row_to_person(row)
    
    async def get_person(self, id: UUID) -> Optional[Person]:
        """Get person by ID with career history."""
        query = "SELECT * FROM persons WHERE id = $1"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, id)
            if not row:
                return None
            
            person = self._row_to_person(row)
            
            # Load career history
            career_query = """
                SELECT ch.*,
                    CASE ch.company_type
                        WHEN 'Supplier' THEN (SELECT name FROM suppliers WHERE id = ch.company_id)
                        WHEN 'Manufacturer' THEN (SELECT name FROM manufacturers WHERE id = ch.company_id)
                    END as company_name
                FROM career_history ch
                WHERE ch.person_id = $1
                ORDER BY ch.start_date DESC
            """
            career_rows = await conn.fetch(career_query, id)
            person.career_history = [self._row_to_career(r) for r in career_rows]
            
            return person
    
    async def find_persons(
        self,
        search: Optional[str] = None,
        company_id: Optional[UUID] = None,
        is_active: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Person]:
        """Find persons with filters."""
        conditions = []
        params = []
        param_idx = 1
        
        if search:
            conditions.append(f"""
                (full_name ILIKE ${param_idx} OR phone ILIKE ${param_idx} 
                 OR email ILIKE ${param_idx} OR telegram_id ILIKE ${param_idx})
            """)
            params.append(f"%{search}%")
            param_idx += 1
        
        if company_id:
            conditions.append(f"""
                id IN (SELECT person_id FROM career_history WHERE company_id = ${param_idx} AND is_current = TRUE)
            """)
            params.append(company_id)
            param_idx += 1
        
        if is_active is not None:
            conditions.append(f"is_active = ${param_idx}")
            params.append(is_active)
            param_idx += 1
        
        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        
        query = f"""
            SELECT * FROM persons
            WHERE {where_clause}
            ORDER BY full_name
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [self._row_to_person(row) for row in rows]
    
    async def find_active_managers(self, company_id: UUID) -> List[Person]:
        """Find people currently working at a company."""
        query = """
            SELECT p.* FROM persons p
            JOIN career_history ch ON ch.person_id = p.id
            WHERE ch.company_id = $1 AND ch.is_current = TRUE AND p.is_active = TRUE
            ORDER BY p.full_name
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, company_id)
        return [self._row_to_person(row) for row in rows]
    
    async def update_person(self, person: Person) -> Person:
        """Update person."""
        query = """
            UPDATE persons SET
                full_name = $2, first_name = $3, last_name = $4, middle_name = $5,
                phone = $6, phone_mobile = $7, email = $8, telegram_id = $9, whatsapp = $10,
                birth_date = $11, gender = $12, notes = $13, interests = $14, preferred_contact_method = $15,
                specialization = $16, is_active = $17, last_contact_date = $18,
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                person.id, person.full_name, person.first_name, person.last_name, person.middle_name,
                person.phone, person.phone_mobile, person.email, person.telegram_id, person.whatsapp,
                person.birth_date, person.gender, person.notes, person.interests, person.preferred_contact_method,
                person.specialization, person.is_active, person.last_contact_date
            )
        return self._row_to_person(row)
    
    def _row_to_person(self, row: asyncpg.Record) -> Person:
        """Convert database row to Person domain object."""
        return Person(
            id=row['id'],
            full_name=row['full_name'],
            first_name=row['first_name'],
            last_name=row['last_name'],
            middle_name=row['middle_name'],
            phone=row['phone'],
            phone_mobile=row['phone_mobile'],
            email=row['email'],
            telegram_id=row['telegram_id'],
            whatsapp=row['whatsapp'],
            birth_date=row['birth_date'],
            gender=row['gender'],
            notes=row['notes'],
            interests=row['interests'],
            preferred_contact_method=row['preferred_contact_method'],
            specialization=row['specialization'],
            is_active=row['is_active'],
            last_contact_date=row['last_contact_date'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )
    
    # ========================================================================
    # CAREER HISTORY
    # ========================================================================
    
    async def add_career_record(self, record: CareerRecord) -> CareerRecord:
        """Add career record (job change)."""
        query = """
            INSERT INTO career_history (
                id, person_id, company_id, company_type,
                role, department, start_date, end_date, is_current,
                work_phone, work_email, notes
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                record.id, record.person_id, record.company_id, record.company_type.value,
                record.role, record.department, record.start_date, record.end_date, record.is_current,
                record.work_phone, record.work_email, record.notes
            )
        return self._row_to_career(row)
    
    async def end_career_record(self, record_id: UUID, end_date: date) -> None:
        """End a career record (person left company)."""
        query = """
            UPDATE career_history SET
                is_current = FALSE, end_date = $2, updated_at = NOW()
            WHERE id = $1
        """
        async with self._pool.acquire() as conn:
            await conn.execute(query, record_id, end_date)
    
    def _row_to_career(self, row: asyncpg.Record) -> CareerRecord:
        """Convert database row to CareerRecord domain object."""
        return CareerRecord(
            id=row['id'],
            person_id=row['person_id'],
            company_id=row['company_id'],
            company_type=CompanyType(row['company_type']),
            role=row['role'],
            department=row.get('department'),
            start_date=row['start_date'],
            end_date=row['end_date'],
            is_current=row['is_current'],
            work_phone=row['work_phone'],
            work_email=row['work_email'],
            notes=row['notes'],
            company_name=row.get('company_name'),
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )
    
    # ========================================================================
    # BIRTHDAYS
    # ========================================================================
    
    async def get_upcoming_birthdays(self, days: int = 7) -> List[dict]:
        """Get contacts with birthdays in the next N days."""
        query = """
            SELECT * FROM upcoming_birthdays
            WHERE days_until_birthday <= $1
            ORDER BY days_until_birthday
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, days)
        return [dict(row) for row in rows]
    
    async def get_birthdays_this_week(self) -> List[dict]:
        """Get contacts with birthdays this week."""
        return await self.get_upcoming_birthdays(7)
    
    async def get_birthdays_today(self) -> List[dict]:
        """Get contacts with birthdays today."""
        return await self.get_upcoming_birthdays(0)
    
    # ========================================================================
    # INTERACTIONS
    # ========================================================================
    
    async def log_interaction(self, interaction: Interaction) -> Interaction:
        """Log an interaction with a contact."""
        query = """
            INSERT INTO interactions (
                id, person_id, interaction_type, direction,
                subject, content, outcome, next_action, next_action_date,
                deal_id, created_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                interaction.id, interaction.person_id,
                interaction.interaction_type.value, interaction.direction.value,
                interaction.subject, interaction.content, interaction.outcome,
                interaction.next_action, interaction.next_action_date,
                interaction.deal_id, interaction.created_by
            )
            
            # Update last contact date
            await conn.execute(
                "UPDATE persons SET last_contact_date = $1 WHERE id = $2",
                date.today(), interaction.person_id
            )
        
        return self._row_to_interaction(row)
    
    async def get_person_interactions(
        self,
        person_id: UUID,
        limit: int = 50
    ) -> List[Interaction]:
        """Get interactions for a person."""
        query = """
            SELECT * FROM interactions
            WHERE person_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, person_id, limit)
        return [self._row_to_interaction(row) for row in rows]
    
    async def get_pending_actions(self) -> List[dict]:
        """Get interactions with pending next actions."""
        query = """
            SELECT i.*, p.full_name as person_name
            FROM interactions i
            JOIN persons p ON p.id = i.person_id
            WHERE i.next_action IS NOT NULL 
              AND i.next_action_date <= CURRENT_DATE + INTERVAL '3 days'
            ORDER BY i.next_action_date
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query)
        return [dict(row) for row in rows]
    
    def _row_to_interaction(self, row: asyncpg.Record) -> Interaction:
        """Convert database row to Interaction domain object."""
        return Interaction(
            id=row['id'],
            person_id=row['person_id'],
            interaction_type=InteractionType(row['interaction_type']),
            direction=InteractionDirection(row['direction']),
            subject=row['subject'],
            content=row['content'],
            outcome=row['outcome'],
            next_action=row['next_action'],
            next_action_date=row['next_action_date'],
            deal_id=row['deal_id'],
            created_by=row['created_by'],
            created_at=row['created_at'],
        )
    
    # ========================================================================
    # SUPPLIER-MANUFACTURER LINKS
    # ========================================================================
    
    async def link_supplier_manufacturer(
        self,
        supplier_id: UUID,
        manufacturer_id: UUID,
        is_official: bool = False,
        discount: Decimal = Decimal("0")
    ) -> SupplierManufacturer:
        """Link supplier to manufacturer."""
        query = """
            INSERT INTO supplier_manufacturers (supplier_id, manufacturer_id, is_official_dealer, discount_percent)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (supplier_id, manufacturer_id) DO UPDATE SET
                is_official_dealer = $3, discount_percent = $4
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, supplier_id, manufacturer_id, is_official, discount)
        return SupplierManufacturer(
            id=row['id'],
            supplier_id=row['supplier_id'],
            manufacturer_id=row['manufacturer_id'],
            is_official_dealer=row['is_official_dealer'],
            discount_percent=Decimal(str(row['discount_percent'])),
            created_at=row['created_at'],
        )
    
    async def get_supplier_manufacturers(self, supplier_id: UUID) -> List[Manufacturer]:
        """Get manufacturers that a supplier sells."""
        query = """
            SELECT m.* FROM manufacturers m
            JOIN supplier_manufacturers sm ON sm.manufacturer_id = m.id
            WHERE sm.supplier_id = $1
            ORDER BY m.name
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, supplier_id)
        return [self._row_to_manufacturer(row) for row in rows]
    
    async def get_manufacturer_suppliers(self, manufacturer_id: UUID) -> List[Supplier]:
        """Get suppliers that sell a manufacturer's products."""
        query = """
            SELECT s.* FROM suppliers s
            JOIN supplier_manufacturers sm ON sm.supplier_id = s.id
            WHERE sm.manufacturer_id = $1
            ORDER BY s.rating DESC, s.name
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, manufacturer_id)
        return [self._row_to_supplier(row) for row in rows]
