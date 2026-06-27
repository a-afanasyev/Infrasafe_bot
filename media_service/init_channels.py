#!/usr/bin/env python3
"""
Скрипт для инициализации каналов в базе данных MediaService
"""

import asyncio
from sqlalchemy.orm import Session
from app.db.database import engine, SessionLocal, Base
from app.models.media import MediaChannel
from app.core.config import settings, TelegramChannels

def init_channels():
    """Инициализация каналов в базе данных"""
    print("🚀 Initializing MediaService Channels...")

    # Создаем таблицы если их нет
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Каналы для создания
        channels_config = [
            {
                'channel_name': 'uk_media_requests_private',
                'channel_id': int(settings.channel_requests),
                'channel_username': '@uk_media_requests_private',
                'purpose': TelegramChannels.REQUESTS,
                'category': None,
                'is_active': True,
                'is_backup_channel': False
            },
            {
                'channel_name': 'uk_media_reports_private',
                'channel_id': int(settings.channel_reports),
                'channel_username': '@uk_media_reports_private',
                'purpose': TelegramChannels.REPORTS,
                'category': None,
                'is_active': True,
                'is_backup_channel': False
            },
            {
                'channel_name': 'uk_media_archive_private',
                'channel_id': int(settings.channel_archive),
                'channel_username': '@uk_media_archive_private',
                'purpose': TelegramChannels.ARCHIVE,
                'category': None,
                'is_active': True,
                'is_backup_channel': False
            },
            {
                'channel_name': 'uk_media_backup_private',
                'channel_id': int(settings.channel_backup),
                'channel_username': '@uk_media_backup_private',
                'purpose': TelegramChannels.BACKUP,
                'category': None,
                'is_active': True,
                'is_backup_channel': True
            }
        ]

        # access — ОПЦИОНАЛЬНЫЙ канал контроля доступа. Добавляем в инициализацию
        # только если CHANNEL_ACCESS сконфигурирован (иначе домен не используется).
        if settings.channel_access:
            channels_config.append({
                'channel_name': 'uk_media_access_private',
                'channel_id': int(settings.channel_access),
                'channel_username': '@uk_media_access_private',
                'purpose': TelegramChannels.ACCESS,
                'category': None,
                'is_active': True,
                'is_backup_channel': False
            })

        for config in channels_config:
            # Проверяем, существует ли канал
            existing = db.query(MediaChannel).filter(
                MediaChannel.purpose == config['purpose']
            ).first()

            if existing:
                # Обновляем существующий
                existing.channel_id = config['channel_id']
                existing.channel_username = config['channel_username']
                existing.is_active = config['is_active']
                print(f"✅ Updated channel: {config['purpose']} (ID: {config['channel_id']})")
            else:
                # Создаем новый
                channel = MediaChannel(**config)
                db.add(channel)
                print(f"✅ Created channel: {config['purpose']} (ID: {config['channel_id']})")

        db.commit()

        # Проверяем результат
        print("\n📋 Channels in database:")
        channels = db.query(MediaChannel).all()
        for channel in channels:
            status = "🟢 Active" if channel.is_active else "🔴 Inactive"
            backup = "💾 Backup" if channel.is_backup_channel else ""
            print(f"   {channel.purpose}: {channel.channel_name} (ID: {channel.channel_id}) {status} {backup}")

        print(f"\n🎉 Successfully initialized {len(channels)} channels!")

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    init_channels()