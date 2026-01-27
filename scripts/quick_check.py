#!/usr/bin/env python
"""Быстрая проверка состояния системы."""

import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, func, desc
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import (
    Tenant,
    UserBotAccount,
    TargetChannel,
    TrafficAction,
)


async def main():
    """Проверка состояния системы."""
    await init_db()

    async with get_session() as session:
        # Tenant
        result = await session.execute(
            select(Tenant).where(Tenant.name == "infobusiness")
        )
        tenant = result.scalar_one_or_none()

        if not tenant:
            print("❌ Tenant not found!")
            return

        print(f"✅ Tenant: {tenant.display_name}\n")

        # Accounts
        result = await session.execute(
            select(UserBotAccount).where(UserBotAccount.tenant_id == tenant.id)
        )
        accounts = result.scalars().all()
        print(f"📱 Accounts: {len(accounts)}")
        for acc in accounts[:4]:
            print(f"   - {acc.first_name} (@{acc.username}) - status: {acc.status}")
        print()

        # Channels
        result = await session.execute(
            select(TargetChannel).where(
                TargetChannel.tenant_id == tenant.id,
                TargetChannel.is_active == True
            )
        )
        channels = result.scalars().all()
        print(f"📺 Active channels: {len(channels)}")

        channels_with_posts = [ch for ch in channels if ch.last_post_id]
        print(f"   - Channels monitored (have last_post_id): {len(channels_with_posts)}")
        print()

        # Comments
        result = await session.execute(
            select(func.count(TrafficAction.id)).where(
                TrafficAction.tenant_id == tenant.id,
                TrafficAction.action_type == "comment"
            )
        )
        total_comments = result.scalar()

        result = await session.execute(
            select(func.count(TrafficAction.id)).where(
                TrafficAction.tenant_id == tenant.id,
                TrafficAction.action_type == "comment",
                TrafficAction.status == "success"
            )
        )
        success_comments = result.scalar()

        print(f"💬 Comments total: {total_comments}")
        print(f"   - Success: {success_comments}")
        print(f"   - Failed/pending: {total_comments - success_comments}")
        print()

        # Last comments
        result = await session.execute(
            select(TrafficAction)
            .where(
                TrafficAction.tenant_id == tenant.id,
                TrafficAction.action_type == "comment"
            )
            .order_by(desc(TrafficAction.created_at))
            .limit(3)
        )
        last_comments = result.scalars().all()

        if last_comments:
            print("🕐 Last comments:")
            for comment in last_comments:
                acc = await session.get(UserBotAccount, comment.account_id)
                acc_name = f"@{acc.username}" if acc else f"ID:{comment.account_id}"
                print(f"   - {comment.created_at.strftime('%H:%M:%S')} - {acc_name} - {comment.status}")
        else:
            print("⚠️  NO COMMENTS YET!")
            print()
            print("📌 REASON: System only comments on NEW posts.")
            print("   When system starts, it saves last_post_id for each channel.")
            print("   It will comment when channels publish NEW posts.")
            print()
            print("💡 SOLUTION: Wait for new posts in channels, or manually trigger comment")
        print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted")
