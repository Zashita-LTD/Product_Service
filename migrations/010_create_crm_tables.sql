-- Migration: 010_create_crm_tables.sql
-- Description: CRM module - Manufacturers, Suppliers, Persons, Career History
-- Date: 2026-01-14

-- ============================================================================
-- 1. MANUFACTURERS (Производители/Бренды)
-- ============================================================================
-- Примеры: Кнауф, Волма, Bosch, Makita
-- Хранит информацию о производителях товаров и наших отношениях с ними

CREATE TABLE IF NOT EXISTS manufacturers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Основная информация
    name VARCHAR(255) UNIQUE NOT NULL,
    name_normalized VARCHAR(255), -- Нормализованное имя для поиска (lowercase, без спецсимволов)
    description TEXT,
    country VARCHAR(100),
    website VARCHAR(255),
    
    -- Партнёрский статус
    partner_status VARCHAR(50) DEFAULT 'None', -- 'None', 'Dealer', 'Distributor', 'Official'
    discount_percent DECIMAL(5,2) DEFAULT 0.0, -- Наша базовая скидка от производителя
    contract_number VARCHAR(100),
    contract_valid_until DATE,
    
    -- Контактная информация (общая)
    support_email VARCHAR(255),
    support_phone VARCHAR(50),
    
    -- AI/Embeddings
    embedding vector(768), -- Вектор описания для AI-поиска
    
    -- Метаданные
    catalogs_url TEXT, -- Ссылка на каталоги PDF
    notes TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индексы для manufacturers
CREATE INDEX IF NOT EXISTS idx_manufacturers_name_normalized ON manufacturers(name_normalized);
CREATE INDEX IF NOT EXISTS idx_manufacturers_partner_status ON manufacturers(partner_status);

-- ============================================================================
-- 2. SUPPLIERS (Поставщики/Дилеры)
-- ============================================================================
-- Примеры: Петрович, СтройДвор, Металл-Сервис, ИП Иванов
-- Это те, у кого мы покупаем товары

CREATE TABLE IF NOT EXISTS suppliers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Основная информация
    name VARCHAR(255) NOT NULL,
    legal_name VARCHAR(255), -- Юр. название (ООО "Ромашка")
    inn VARCHAR(20),
    kpp VARCHAR(20),
    ogrn VARCHAR(20),
    
    -- Контактная информация
    website VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(50),
    address TEXT,
    
    -- Рейтинг и оценка
    rating DECIMAL(3,2) DEFAULT 0.0, -- 0.00 - 5.00
    reliability_score DECIMAL(3,2) DEFAULT 0.0, -- Надёжность доставки
    price_score DECIMAL(3,2) DEFAULT 0.0, -- Конкурентность цен
    total_orders INTEGER DEFAULT 0,
    successful_orders INTEGER DEFAULT 0,
    
    -- Условия работы
    payment_terms VARCHAR(100), -- 'Prepay', 'Net30', 'Net60'
    delivery_days INTEGER, -- Среднее время доставки
    min_order_amount DECIMAL(12,2), -- Минимальный заказ
    
    -- Статус
    status VARCHAR(50) DEFAULT 'Active', -- 'Active', 'Inactive', 'Blacklisted'
    blacklist_reason TEXT,
    
    -- Метаданные
    notes TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индексы для suppliers
CREATE INDEX IF NOT EXISTS idx_suppliers_inn ON suppliers(inn);
CREATE INDEX IF NOT EXISTS idx_suppliers_status ON suppliers(status);
CREATE INDEX IF NOT EXISTS idx_suppliers_rating ON suppliers(rating DESC);

-- ============================================================================
-- 3. PERSONS (Контакты/Менеджеры)
-- ============================================================================
-- Люди, с которыми мы работаем. Самый ценный актив CRM!
-- Фишка: человек не привязан к компании намертво, он может переходить

CREATE TABLE IF NOT EXISTS persons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Основная информация
    full_name VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    middle_name VARCHAR(100),
    
    -- Контакты
    phone VARCHAR(50),
    phone_mobile VARCHAR(50),
    email VARCHAR(255),
    telegram_id VARCHAR(100),
    whatsapp VARCHAR(50),
    
    -- CRM данные (для построения отношений)
    birth_date DATE,
    gender VARCHAR(20), -- 'Male', 'Female', 'Unknown'
    
    -- Личные заметки (конфиденциально!)
    notes TEXT, -- "Любит рыбалку, коньяк Hennessy"
    interests TEXT, -- "Футбол, охота"
    preferred_contact_method VARCHAR(50), -- 'Phone', 'Telegram', 'Email'
    
    -- Профессиональные данные
    specialization VARCHAR(255), -- "Сухие смеси", "Электроинструмент"
    
    -- Статус
    is_active BOOLEAN DEFAULT TRUE,
    last_contact_date DATE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индексы для persons
CREATE INDEX IF NOT EXISTS idx_persons_phone ON persons(phone);
CREATE INDEX IF NOT EXISTS idx_persons_email ON persons(email);
CREATE INDEX IF NOT EXISTS idx_persons_telegram ON persons(telegram_id);
CREATE INDEX IF NOT EXISTS idx_persons_birth_date ON persons(birth_date);

-- ============================================================================
-- 4. CAREER_HISTORY (История карьеры)
-- ============================================================================
-- Где человек работал и работает сейчас
-- Позволяет отследить переходы между компаниями

CREATE TABLE IF NOT EXISTS career_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Связи
    person_id UUID NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    company_id UUID NOT NULL, -- Ссылка на suppliers.id или manufacturers.id
    company_type VARCHAR(20) NOT NULL, -- 'Supplier' или 'Manufacturer'
    
    -- Должность
    role VARCHAR(255), -- "Менеджер по продажам", "Директор"
    department VARCHAR(255), -- "Отдел продаж", "Закупки"
    
    -- Период работы
    start_date DATE NOT NULL,
    end_date DATE, -- NULL = работает сейчас
    is_current BOOLEAN DEFAULT FALSE,
    
    -- Контактные данные на этой работе (могут отличаться от личных)
    work_phone VARCHAR(50),
    work_email VARCHAR(255),
    
    -- Метаданные
    notes TEXT, -- "Хороший контакт, быстро отвечает"
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индексы для career_history
CREATE INDEX IF NOT EXISTS idx_career_person ON career_history(person_id);
CREATE INDEX IF NOT EXISTS idx_career_company ON career_history(company_id, company_type);
CREATE INDEX IF NOT EXISTS idx_career_current ON career_history(is_current) WHERE is_current = TRUE;

-- ============================================================================
-- 5. SUPPLIER_MANUFACTURERS (Связь: какие бренды продаёт поставщик)
-- ============================================================================

CREATE TABLE IF NOT EXISTS supplier_manufacturers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    supplier_id UUID NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    manufacturer_id UUID NOT NULL REFERENCES manufacturers(id) ON DELETE CASCADE,
    
    -- Условия
    is_official_dealer BOOLEAN DEFAULT FALSE,
    discount_percent DECIMAL(5,2) DEFAULT 0.0, -- Скидка этого поставщика на этот бренд
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(supplier_id, manufacturer_id)
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_supplier_manufacturers_supplier ON supplier_manufacturers(supplier_id);
CREATE INDEX IF NOT EXISTS idx_supplier_manufacturers_manufacturer ON supplier_manufacturers(manufacturer_id);

-- ============================================================================
-- 6. INTERACTIONS (История взаимодействий)
-- ============================================================================
-- Лог всех контактов с людьми

CREATE TABLE IF NOT EXISTS interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    person_id UUID NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    
    -- Тип взаимодействия
    interaction_type VARCHAR(50) NOT NULL, -- 'Call', 'Email', 'Meeting', 'Message', 'Gift'
    direction VARCHAR(20) NOT NULL, -- 'Inbound', 'Outbound'
    
    -- Контент
    subject VARCHAR(500),
    content TEXT,
    
    -- Результат
    outcome VARCHAR(100), -- 'Success', 'No Answer', 'Callback', 'Deal'
    next_action VARCHAR(500),
    next_action_date DATE,
    
    -- Связь со сделкой (если есть)
    deal_id UUID, -- Ссылка на будущую таблицу deals
    
    -- Кто провёл
    created_by VARCHAR(100), -- Наш сотрудник
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индексы для interactions
CREATE INDEX IF NOT EXISTS idx_interactions_person ON interactions(person_id);
CREATE INDEX IF NOT EXISTS idx_interactions_date ON interactions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_interactions_next_action ON interactions(next_action_date) WHERE next_action_date IS NOT NULL;

-- ============================================================================
-- 7. BIRTHDAYS VIEW (Кого поздравить)
-- ============================================================================

CREATE OR REPLACE VIEW upcoming_birthdays AS
SELECT 
    p.id,
    p.full_name,
    p.birth_date,
    p.phone,
    p.telegram_id,
    p.notes,
    ch.role,
    CASE ch.company_type
        WHEN 'Supplier' THEN (SELECT name FROM suppliers WHERE id = ch.company_id)
        WHEN 'Manufacturer' THEN (SELECT name FROM manufacturers WHERE id = ch.company_id)
    END as company_name,
    -- Дней до ДР
    CASE 
        WHEN EXTRACT(DOY FROM p.birth_date::date) >= EXTRACT(DOY FROM CURRENT_DATE)
        THEN EXTRACT(DOY FROM p.birth_date::date) - EXTRACT(DOY FROM CURRENT_DATE)
        ELSE 365 - EXTRACT(DOY FROM CURRENT_DATE) + EXTRACT(DOY FROM p.birth_date::date)
    END::INTEGER as days_until_birthday
FROM persons p
LEFT JOIN career_history ch ON ch.person_id = p.id AND ch.is_current = TRUE
WHERE p.birth_date IS NOT NULL AND p.is_active = TRUE
ORDER BY days_until_birthday;

-- ============================================================================
-- 8. TRIGGERS (Автоматизация)
-- ============================================================================

-- Триггер: обновление updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Применяем триггеры
DROP TRIGGER IF EXISTS update_manufacturers_updated_at ON manufacturers;
CREATE TRIGGER update_manufacturers_updated_at
    BEFORE UPDATE ON manufacturers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_suppliers_updated_at ON suppliers;
CREATE TRIGGER update_suppliers_updated_at
    BEFORE UPDATE ON suppliers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_persons_updated_at ON persons;
CREATE TRIGGER update_persons_updated_at
    BEFORE UPDATE ON persons
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_career_updated_at ON career_history;
CREATE TRIGGER update_career_updated_at
    BEFORE UPDATE ON career_history
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Триггер: при смене работы, закрыть предыдущую запись
CREATE OR REPLACE FUNCTION close_previous_career()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_current = TRUE THEN
        UPDATE career_history 
        SET is_current = FALSE, 
            end_date = COALESCE(end_date, NEW.start_date)
        WHERE person_id = NEW.person_id 
          AND id != NEW.id 
          AND is_current = TRUE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS career_change_trigger ON career_history;
CREATE TRIGGER career_change_trigger
    AFTER INSERT OR UPDATE ON career_history
    FOR EACH ROW EXECUTE FUNCTION close_previous_career();

-- ============================================================================
-- COMMENTS
-- ============================================================================
COMMENT ON TABLE manufacturers IS 'Производители товаров (бренды): Кнауф, Волма, Bosch';
COMMENT ON TABLE suppliers IS 'Поставщики/дилеры: Петрович, СтройДвор, ИП Иванов';
COMMENT ON TABLE persons IS 'Контакты - менеджеры поставщиков и производителей';
COMMENT ON TABLE career_history IS 'История карьеры контактов - где работали и работают';
COMMENT ON TABLE interactions IS 'Лог взаимодействий с контактами';
COMMENT ON VIEW upcoming_birthdays IS 'Список предстоящих дней рождения контактов';
