"""
Миграция для добавления справочника адресов с модерацией.

Добавляет:
- yards - дворы (территории управляющей компании)
- buildings - здания (дома)
- apartments - квартиры
- user_apartments - связь пользователей с квартирами (с модерацией)

Изменяет:
- users - удаляет legacy поля адресов (address, home_address, apartment_address, yard_address, address_type)
- requests - добавляет apartment_id FK, делает address nullable

Дата создания: 2025-01-21
"""

from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


def upgrade(engine):
    """Применяет миграцию - создает новые таблицы и изменяет существующие."""
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            logger.info("Начало миграции: добавление справочника адресов")

            # 1. Создаем таблицу yards (дворы)
            logger.info("Создание таблицы yards...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS yards (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(200) NOT NULL UNIQUE,
                    description TEXT,
                    gps_latitude FLOAT,
                    gps_longitude FLOAT,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    created_by INTEGER REFERENCES users(id),
                    updated_at TIMESTAMP WITH TIME ZONE
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_yards_name ON yards(name)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_yards_is_active ON yards(is_active)"))

            # 2. Создаем таблицу buildings (здания)
            logger.info("Создание таблицы buildings...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS buildings (
                    id SERIAL PRIMARY KEY,
                    address VARCHAR(300) NOT NULL,
                    yard_id INTEGER NOT NULL REFERENCES yards(id) ON DELETE CASCADE,
                    gps_latitude FLOAT,
                    gps_longitude FLOAT,
                    entrance_count INTEGER NOT NULL DEFAULT 1,
                    floor_count INTEGER NOT NULL DEFAULT 1,
                    description TEXT,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    created_by INTEGER REFERENCES users(id),
                    updated_at TIMESTAMP WITH TIME ZONE
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_buildings_address ON buildings(address)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_buildings_yard_id ON buildings(yard_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_buildings_is_active ON buildings(is_active)"))

            # 3. Создаем таблицу apartments (квартиры)
            logger.info("Создание таблицы apartments...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS apartments (
                    id SERIAL PRIMARY KEY,
                    building_id INTEGER NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
                    apartment_number VARCHAR(20) NOT NULL,
                    entrance INTEGER,
                    floor INTEGER,
                    rooms_count INTEGER,
                    area FLOAT,
                    description TEXT,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    created_by INTEGER REFERENCES users(id),
                    updated_at TIMESTAMP WITH TIME ZONE,
                    CONSTRAINT uix_building_apartment UNIQUE (building_id, apartment_number)
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_apartments_building_id ON apartments(building_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_apartments_number ON apartments(apartment_number)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_apartments_is_active ON apartments(is_active)"))

            # 4. Создаем таблицу user_apartments (связь пользователей с квартирами с модерацией)
            logger.info("Создание таблицы user_apartments...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_apartments (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    apartment_id INTEGER NOT NULL REFERENCES apartments(id) ON DELETE CASCADE,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    requested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    reviewed_at TIMESTAMP WITH TIME ZONE,
                    reviewed_by INTEGER REFERENCES users(id),
                    admin_comment TEXT,
                    is_owner BOOLEAN NOT NULL DEFAULT FALSE,
                    is_primary BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE,
                    CONSTRAINT uix_user_apartment UNIQUE (user_id, apartment_id)
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_apartments_user_id ON user_apartments(user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_apartments_apartment_id ON user_apartments(apartment_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_apartments_status ON user_apartments(status)"))

            # 5. Изменяем таблицу users - удаляем legacy поля адресов
            logger.info("Обновление таблицы users - удаление legacy полей адресов...")

            # Проверяем существование каждой колонки перед удалением
            legacy_columns = ['address', 'home_address', 'apartment_address', 'yard_address', 'address_type']

            for column in legacy_columns:
                # Проверяем существование колонки
                result = conn.execute(text(f"""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = '{column}'
                """))

                if result.fetchone():
                    logger.info(f"Удаление колонки {column} из таблицы users...")
                    conn.execute(text(f"ALTER TABLE users DROP COLUMN IF EXISTS {column}"))
                else:
                    logger.info(f"Колонка {column} не существует, пропускаем...")

            # 6. Изменяем таблицу requests - добавляем apartment_id FK
            logger.info("Обновление таблицы requests...")

            # Проверяем существование колонки apartment_id
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'requests' AND column_name = 'apartment_id'
            """))

            if not result.fetchone():
                logger.info("Добавление колонки apartment_id в таблицу requests...")
                conn.execute(text("""
                    ALTER TABLE requests
                    ADD COLUMN apartment_id INTEGER REFERENCES apartments(id)
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_requests_apartment_id ON requests(apartment_id)"))
            else:
                logger.info("Колонка apartment_id уже существует в таблице requests")

            # Делаем address nullable (если она NOT NULL)
            result = conn.execute(text("""
                SELECT is_nullable
                FROM information_schema.columns
                WHERE table_name = 'requests' AND column_name = 'address'
            """))
            row = result.fetchone()
            if row and row[0] == 'NO':
                logger.info("Изменение колонки address в таблице requests на nullable...")
                conn.execute(text("ALTER TABLE requests ALTER COLUMN address DROP NOT NULL"))
            else:
                logger.info("Колонка address уже nullable или не существует")

            transaction.commit()
            logger.info("✅ Миграция успешно применена: справочник адресов создан")

        except Exception as e:
            transaction.rollback()
            logger.error(f"❌ Ошибка при применении миграции: {e}")
            raise


def downgrade(engine):
    """Откатывает миграцию - удаляет новые таблицы и восстанавливает старые поля."""
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            logger.info("Начало отката миграции: удаление справочника адресов")

            # 1. Удаляем apartment_id из requests
            logger.info("Удаление apartment_id из таблицы requests...")
            conn.execute(text("ALTER TABLE requests DROP COLUMN IF EXISTS apartment_id"))

            # Восстанавливаем NOT NULL для address
            logger.info("Восстановление NOT NULL для address в таблице requests...")
            # Сначала заполняем NULL значения дефолтными
            conn.execute(text("""
                UPDATE requests
                SET address = 'Не указан'
                WHERE address IS NULL
            """))
            conn.execute(text("ALTER TABLE requests ALTER COLUMN address SET NOT NULL"))

            # 2. Восстанавливаем legacy поля в users
            logger.info("Восстановление legacy полей адресов в таблице users...")
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS address TEXT"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS home_address TEXT"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS apartment_address TEXT"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS yard_address TEXT"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS address_type VARCHAR(20)"))

            # 3. Удаляем таблицы в обратном порядке (из-за FK)
            logger.info("Удаление таблиц справочника адресов...")
            conn.execute(text("DROP TABLE IF EXISTS user_apartments CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS apartments CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS buildings CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS yards CASCADE"))

            transaction.commit()
            logger.info("✅ Откат миграции успешно выполнен")

        except Exception as e:
            transaction.rollback()
            logger.error(f"❌ Ошибка при откате миграции: {e}")
            raise


def check_migration_status(engine):
    """Проверяет статус миграции - применена или нет."""
    with engine.connect() as conn:
        try:
            # Проверяем существование таблицы yards
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'yards'
                )
            """))
            tables_exist = result.scalar()

            # Проверяем существование колонки apartment_id в requests
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_name = 'requests' AND column_name = 'apartment_id'
                )
            """))
            apartment_id_exists = result.scalar()

            # Проверяем отсутствие legacy полей в users
            result = conn.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = 'users'
                AND column_name IN ('address', 'home_address', 'apartment_address', 'yard_address', 'address_type')
            """))
            legacy_fields_count = result.scalar()

            if tables_exist and apartment_id_exists and legacy_fields_count == 0:
                logger.info("✅ Миграция применена полностью")
                return True
            elif not tables_exist and not apartment_id_exists:
                logger.info("⚠️ Миграция не применена")
                return False
            else:
                logger.warning("⚠️ Миграция применена частично - требуется ручное вмешательство")
                logger.info(f"Таблицы существуют: {tables_exist}")
                logger.info(f"apartment_id существует: {apartment_id_exists}")
                logger.info(f"Legacy поля в users: {legacy_fields_count}")
                return None

        except Exception as e:
            logger.error(f"❌ Ошибка при проверке статуса миграции: {e}")
            return None


if __name__ == "__main__":
    """
    Запуск миграции напрямую:
    python add_address_directory.py [upgrade|downgrade|check]
    """
    import sys
    import os
    from sqlalchemy import create_engine

    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Получаем DATABASE_URL из переменных окружения
    database_url = os.getenv('DATABASE_URL', 'postgresql://uk_bot:uk_bot_password@localhost:5432/uk_management')

    engine = create_engine(database_url)

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "upgrade":
            upgrade(engine)
        elif command == "downgrade":
            downgrade(engine)
        elif command == "check":
            check_migration_status(engine)
        else:
            print("Использование: python add_address_directory.py [upgrade|downgrade|check]")
    else:
        print("Использование: python add_address_directory.py [upgrade|downgrade|check]")
