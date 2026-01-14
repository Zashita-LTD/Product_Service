-- Seed data: Sample products for demo

-- Insert sample products
INSERT INTO product_families (name_technical, category_id, quality_score, enrichment_status, brand, description, sku)
VALUES 
    ('Кабель силовой ВВГнг(А)-LS 3x2.5 мм² ГОСТ', 1, 0.95, 'enriched', 'Электрокабель', 'Кабель силовой с медными жилами, ПВХ изоляция, негорючий, с низким дымо- и газовыделением. Сечение 3x2.5 мм², для стационарной прокладки', 'VVG-3x2.5'),
    ('Кабель силовой ВВГнг(А)-LS 5x4 мм² ГОСТ', 1, 0.92, 'enriched', 'Электрокабель', 'Кабель силовой с медными жилами, ПВХ изоляция, негорючий. Сечение 5x4 мм², для стационарной прокладки в помещениях', 'VVG-5x4'),
    ('Автоматический выключатель ABB S201 C16', 2, 0.98, 'enriched', 'ABB', 'Автоматический выключатель модульный, 1P, 16А, характеристика C, 6кА. Для защиты цепей от перегрузок и коротких замыканий', 'ABB-S201-C16'),
    ('Автоматический выключатель ABB S203 C25', 2, 0.97, 'enriched', 'ABB', 'Автоматический выключатель модульный, 3P, 25А, характеристика C, 6кА. Для защиты трехфазных цепей', 'ABB-S203-C25'),
    ('УЗО ABB F202 AC-25/0.03', 2, 0.96, 'enriched', 'ABB', 'Устройство защитного отключения, 2P, 25А, 30мА, тип AC. Защита от поражения электрическим током', 'ABB-F202-25'),
    ('Щит распределительный ЩРН-П-12 IP41', 3, 0.89, 'enriched', 'IEK', 'Щит распределительный навесной, пластиковый корпус, на 12 модулей, IP41. Для установки автоматов и УЗО', 'IEK-SHRN-12'),
    ('Розетка двойная с заземлением Schneider Electric Sedna', 4, 0.94, 'enriched', 'Schneider Electric', 'Розетка электрическая двойная с заземляющим контактом, 16А, 250В. Серия Sedna, белый цвет', 'SE-SDN-2R'),
    ('Выключатель одноклавишный Legrand Valena Life', 4, 0.93, 'enriched', 'Legrand', 'Выключатель одноклавишный, 10А, 250В. Серия Valena Life, белый цвет, для скрытой проводки', 'LGR-VL-1K'),
    ('Светильник LED панель 36W 4000K', 5, 0.88, 'enriched', 'Varton', 'Светодиодный светильник встраиваемый, 36Вт, 4000K нейтральный белый, 3600лм, 595x595мм. Для подвесных потолков', 'VAR-LED-36'),
    ('Лампа LED E27 12W 4000K', 5, 0.91, 'enriched', 'Gauss', 'Светодиодная лампа, цоколь E27, 12Вт, 4000K нейтральный белый, 1150лм, срок службы 25000 часов', 'GAUSS-E27-12'),
    ('Труба гофрированная ПВХ d20 мм серая', 6, 0.85, 'enriched', 'DKC', 'Труба гофрированная из ПВХ, диаметр 20мм, серый цвет, для прокладки кабеля. Самозатухающая, степень защиты IP55', 'DKC-GOFR-20'),
    ('Кабель-канал 40x25 мм белый', 6, 0.87, 'enriched', 'Ecoplast', 'Кабель-канал пластиковый, размер 40x25мм, белый цвет. Для открытой прокладки кабеля в помещениях', 'ECO-KK-40x25'),
    ('Наконечник НШВИ 1.5-8', 7, 0.82, 'enriched', 'КВТ', 'Наконечник штыревой втулочный изолированный, для провода сечением 1.5 мм², длина контакта 8мм', 'KVT-NSHVI-1.5'),
    ('Клеммник WAGO 221-413', 7, 0.95, 'enriched', 'WAGO', 'Клеммник рычажковый универсальный, 3 провода, сечение 0.14-4 мм². Многоразовое соединение, прозрачный корпус', 'WAGO-221-413'),
    ('Изолента ПВХ 19мм x 20м синяя', 8, 0.78, 'enriched', '3M', 'Изоляционная лента ПВХ, ширина 19мм, длина 20м, синий цвет. Для изоляции электрических соединений', '3M-ISO-BLUE')
ON CONFLICT DO NOTHING;

-- Add prices for products
INSERT INTO prices (product_family_uuid, amount, currency, supplier_id, is_active)
SELECT uuid, 
    CASE 
        WHEN name_technical LIKE '%кабель%' THEN 85.50
        WHEN name_technical LIKE '%автомат%' THEN 450.00
        WHEN name_technical LIKE '%УЗО%' THEN 1250.00
        WHEN name_technical LIKE '%щит%' THEN 890.00
        WHEN name_technical LIKE '%розетка%' THEN 320.00
        WHEN name_technical LIKE '%выключатель%' THEN 280.00
        WHEN name_technical LIKE '%светильник%' THEN 1450.00
        WHEN name_technical LIKE '%лампа%' THEN 195.00
        WHEN name_technical LIKE '%труба%' THEN 12.50
        WHEN name_technical LIKE '%кабель-канал%' THEN 45.00
        WHEN name_technical LIKE '%наконечник%' THEN 2.50
        WHEN name_technical LIKE '%клеммник%' THEN 85.00
        ELSE 100.00
    END,
    'RUB',
    1,
    true
FROM product_families
WHERE NOT EXISTS (SELECT 1 FROM prices WHERE prices.product_family_uuid = product_families.uuid);

-- Add some inventory
INSERT INTO inventory (product_family_uuid, warehouse_id, quantity, unit, min_stock_level)
SELECT uuid, 1, 
    CASE 
        WHEN name_technical LIKE '%кабель%' THEN 5000
        WHEN name_technical LIKE '%автомат%' THEN 200
        WHEN name_technical LIKE '%УЗО%' THEN 50
        WHEN name_technical LIKE '%щит%' THEN 30
        WHEN name_technical LIKE '%розетка%' THEN 500
        WHEN name_technical LIKE '%выключатель%' THEN 300
        WHEN name_technical LIKE '%светильник%' THEN 100
        WHEN name_technical LIKE '%лампа%' THEN 1000
        WHEN name_technical LIKE '%труба%' THEN 10000
        WHEN name_technical LIKE '%наконечник%' THEN 50000
        WHEN name_technical LIKE '%клеммник%' THEN 5000
        ELSE 100
    END,
    CASE 
        WHEN name_technical LIKE '%кабель%' THEN 'м'
        WHEN name_technical LIKE '%труба%' THEN 'м'
        ELSE 'шт'
    END,
    100
FROM product_families
WHERE NOT EXISTS (SELECT 1 FROM inventory WHERE inventory.product_family_uuid = product_families.uuid);

-- Add product attributes
INSERT INTO product_attributes (product_uuid, name, value, unit)
SELECT uuid, 'Напряжение', '220-240', 'В' FROM product_families WHERE name_technical LIKE '%автомат%' OR name_technical LIKE '%УЗО%'
ON CONFLICT DO NOTHING;

INSERT INTO product_attributes (product_uuid, name, value, unit)
SELECT uuid, 'Сечение', 
    CASE 
        WHEN name_technical LIKE '%3x2.5%' THEN '3x2.5'
        WHEN name_technical LIKE '%5x4%' THEN '5x4'
        ELSE '2.5'
    END, 
    'мм²' 
FROM product_families WHERE name_technical LIKE '%кабель силовой%'
ON CONFLICT DO NOTHING;

-- Verify data
SELECT 'Products:' as info, count(*) FROM product_families
UNION ALL
SELECT 'Prices:', count(*) FROM prices
UNION ALL
SELECT 'Inventory:', count(*) FROM inventory
UNION ALL
SELECT 'Attributes:', count(*) FROM product_attributes;
