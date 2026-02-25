"""Sync on-chain player count into the API database."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from models import Tournament

DB_URL = "sqlite+aiosqlite:///./clawgame.db"

async def main():
    engine = create_async_engine(DB_URL)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        result = await db.execute(select(Tournament).where(Tournament.chain_id == 0))
        bronze = result.scalar_one_or_none()
        if bronze:
            bronze.player_count = 5
            bronze.prize_pool = str(1000 * 5 * 10**18)  # 5000 GAME in wei
            await db.commit()
            print(f"Bronze tournament updated: player_count=5, prize_pool={bronze.prize_pool}")
        else:
            print("Bronze tournament not found")
    await engine.dispose()

asyncio.run(main())
