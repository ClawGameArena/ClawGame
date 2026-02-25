"""Pre-seed database with existing on-chain tournaments (IDs 0, 1, 2)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Import models
from models import Base, Tournament, TournamentState, GameVariant

DB_URL = "sqlite+aiosqlite:///./clawgame.db"

async def main():
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        # Tournament 0 = Bronze, 1 = Silver, 2 = Gold (already on-chain)
        tournaments = [
            Tournament(chain_id=0, arena=0, entry_fee_game="1000000000000000000000", state=TournamentState.OPEN, variant=GameVariant.CLASSIC),
            Tournament(chain_id=1, arena=1, entry_fee_game="10000000000000000000000", state=TournamentState.OPEN, variant=GameVariant.CLASSIC),
            Tournament(chain_id=2, arena=2, entry_fee_game="100000000000000000000000", state=TournamentState.OPEN, variant=GameVariant.CLASSIC),
        ]
        for t in tournaments:
            db.add(t)
        await db.commit()
        print("Seeded 3 tournaments (Bronze=0, Silver=1, Gold=2)")

    await engine.dispose()

asyncio.run(main())
