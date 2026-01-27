#!/usr/bin/env python
"""
Initialize database for Traffic Engine.

Creates all tables and optionally seeds initial data.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from traffic_engine.database import init_db, get_session, Base
from traffic_engine.database.models import Tenant


async def create_tables():
    """Create all database tables."""
    logger.info("Creating database tables...")
    await init_db()
    logger.info("Tables created successfully!")


async def seed_tenants():
    """Create initial tenants."""
    logger.info("Seeding tenants...")

    tenants_data = [
        {
            "name": "infobusiness",
            "display_name": "Инфобизнес - Курсы по заработку",
            "description": "Привлечение трафика для продажи курсов по онлайн-заработку",
            "config_path": "tenants/infobusiness/config.yaml",
            "funnel_link": "https://t.me/infobiz_bot?start=traffic",
            "max_accounts": 5,
            "max_daily_comments": 200,
            "max_daily_invites": 150,
        },
        {
            "name": "nl_international",
            "display_name": "NL International - Здоровье и питание",
            "description": "Привлечение трафика для NL International",
            "config_path": "tenants/nl_international/config.yaml",
            "funnel_link": "https://t.me/nl_curator_bot?start=traffic",
            "max_accounts": 5,
            "max_daily_comments": 200,
            "max_daily_invites": 150,
        },
    ]

    async with get_session() as session:
        for data in tenants_data:
            # Check if exists
            from sqlalchemy import select
            result = await session.execute(
                select(Tenant).where(Tenant.name == data["name"])
            )
            existing = result.scalar_one_or_none()

            if existing:
                logger.info(f"Tenant '{data['name']}' already exists, skipping")
                continue

            tenant = Tenant(**data)
            session.add(tenant)
            logger.info(f"Created tenant: {data['name']}")

        await session.commit()

    logger.info("Tenants seeded successfully!")


async def main():
    """Main function."""
    logger.info("=== Traffic Engine Database Initialization ===")

    await create_tables()
    await seed_tenants()

    logger.info("=== Database initialization complete! ===")


if __name__ == "__main__":
    asyncio.run(main())
