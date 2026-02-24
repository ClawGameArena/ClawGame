"""
Claw Game — API Server v1.1

FastAPI backend for the Claw Game PvP Battle Royale.
Handles agent registration, tournament management, commit-reveal rounds.

Fixes from audit:
- Rate limiting per IP
- Consistent API response format (always { tournaments: [...] })
- Leaderboard endpoint
- On-chain payment verification
- Proper health check paths
- /contract endpoint for frontend config
"""
import os
import json
import secrets
import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from config import config
from models import (
    Base, Agent, Tournament, TournamentEntry, Round, RoundCommit,
    TournamentState, ArenaType, GameVariant,
)
from game_engine import GameEngine
from blockchain import get_blockchain

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
#                    DATABASE
# ═══════════════════════════════════════════════════════

engine = create_async_engine(config.DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ═══════════════════════════════════════════════════════
#                  RATE LIMITER
# ═══════════════════════════════════════════════════════

class RateLimiter:
    def __init__(self, max_per_minute: int = 30):
        self.max_per_minute = max_per_minute
        self.requests: dict[str, list[float]] = defaultdict(list)

    def is_limited(self, ip: str) -> bool:
        now = time.time()
        window = now - 60
        self.requests[ip] = [t for t in self.requests[ip] if t > window]
        if len(self.requests[ip]) >= self.max_per_minute:
            return True
        self.requests[ip].append(now)
        return False

rate_limiter = RateLimiter(config.RATE_LIMIT_PER_MINUTE)


# ═══════════════════════════════════════════════════════
#                    STARTUP
# ═══════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Claw Game API v1.1 started")
    task = asyncio.create_task(tournament_manager())
    yield
    task.cancel()

app = FastAPI(
    title="Claw Game API",
    description="PvP Battle Royale Arena for AI Agents",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path in ("/health", "/", "/api/v1/health"):
        return await call_next(request)
    ip = request.client.host if request.client else "unknown"
    if rate_limiter.is_limited(ip):
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Max 30 requests per minute."},
        )
    return await call_next(request)


# ═══════════════════════════════════════════════════════
#                  AUTH HELPER
# ═══════════════════════════════════════════════════════

async def get_agent(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> Agent:
    result = await db.execute(select(Agent).where(Agent.api_key == x_api_key))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(401, "Invalid API key")
    if agent.status != "active":
        raise HTTPException(403, f"Agent is {agent.status}")
    return agent


# ═══════════════════════════════════════════════════════
#                REQUEST MODELS
# ═══════════════════════════════════════════════════════

class RegisterRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    creator_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    name: str = Field(default="", max_length=100)

class CommitRequest(BaseModel):
    commit_hash: str = Field(..., pattern="^0x[a-fA-F0-9]{64}$")

class RevealRequest(BaseModel):
    bid: int = Field(..., ge=1, le=1000)
    salt: str = Field(..., pattern="^0x[a-fA-F0-9]{64}$")


# ═══════════════════════════════════════════════════════
#                 HELPERS
# ═══════════════════════════════════════════════════════

def _format_tournament(t: Tournament) -> dict:
    arena_usd = config.ARENA_FEES_USD.get(t.arena, 5)
    return {
        "id": t.id,
        "chain_id": t.chain_id,
        "arena": t.arena,
        "arena_name": ArenaType(t.arena).name,
        "state": t.state,
        "state_name": TournamentState(t.state).name,
        "phase": _state_to_phase(t.state),
        "variant": t.variant,
        "variant_name": GameVariant(t.variant).name,
        "entry_fee_game": str(t.entry_fee_game),
        "entry_fee_usd": arena_usd,
        "player_count": t.player_count,
        "max_players": config.MAX_PLAYERS,
        "prize_pool": str(t.prize_pool),
        "current_round": t.current_round,
        "round": t.current_round,
        "phase_deadline": t.phase_deadline.isoformat() if t.phase_deadline else None,
        "created_at": t.created_at.isoformat(),
        "winner": t.winner_address,
        "finalists": json.loads(t.finalist_addresses) if t.finalist_addresses else [],
        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
    }

def _state_to_phase(state: int) -> str:
    mapping = {
        TournamentState.OPEN: "registration",
        TournamentState.ACTIVE: "active",
        TournamentState.COMMIT: "commit",
        TournamentState.REVEAL: "reveal",
        TournamentState.RESOLVING: "resolving",
        TournamentState.FINISHED: "finished",
        TournamentState.CANCELLED: "cancelled",
    }
    return mapping.get(state, "unknown")


# ═══════════════════════════════════════════════════════
#             AGENT REGISTRATION
# ═══════════════════════════════════════════════════════

@app.post("/api/v1/agents/register")
async def register_agent(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(Agent).where(Agent.wallet_address == req.wallet_address.lower())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Agent already registered with this wallet")

    api_key = secrets.token_hex(32)
    agent = Agent(
        wallet_address=req.wallet_address.lower(),
        creator_address=req.creator_address.lower(),
        name=req.name or f"Agent-{req.wallet_address[-6:]}",
        api_key=api_key,
    )
    db.add(agent)
    await db.flush()

    return {
        "agent_id": agent.id,
        "api_key": api_key,
        "wallet_address": agent.wallet_address,
        "creator_address": agent.creator_address,
        "message": "Agent registered. Use X-API-Key header for all requests.",
    }


# ═══════════════════════════════════════════════════════
#             TOURNAMENT ENDPOINTS
# ═══════════════════════════════════════════════════════

@app.get("/api/v1/tournaments/current")
async def get_current_tournaments(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Tournament).where(
            Tournament.state.in_([
                TournamentState.OPEN, TournamentState.ACTIVE,
                TournamentState.COMMIT, TournamentState.REVEAL,
                TournamentState.RESOLVING,
            ])
        ).order_by(Tournament.arena)
    )
    tournaments = result.scalars().all()
    return {"tournaments": [_format_tournament(t) for t in tournaments]}


@app.post("/api/v1/tournaments/{tournament_id}/join")
async def join_tournament(
    tournament_id: int, req: CommitRequest,
    agent: Agent = Depends(get_agent), db: AsyncSession = Depends(get_db),
):
    tournament = await db.get(Tournament, tournament_id)
    if not tournament:
        raise HTTPException(404, "Tournament not found")
    if tournament.state != TournamentState.OPEN:
        raise HTTPException(400, "Tournament not open for registration")
    if tournament.player_count >= config.MAX_PLAYERS:
        raise HTTPException(400, "Tournament full")

    existing = await db.execute(
        select(TournamentEntry).where(and_(
            TournamentEntry.tournament_id == tournament_id,
            TournamentEntry.agent_id == agent.id,
        ))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Already joined this tournament")

    # On-chain payment verification (best-effort)
    try:
        bc = get_blockchain()
        if bc.contract and tournament.chain_id is not None:
            paid = bc.verify_player_joined(tournament.chain_id, agent.wallet_address)
            if not paid:
                raise HTTPException(402, "Entry fee not paid on-chain. Call join() or joinWithETH() on the contract first.")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"On-chain verification skipped: {e}")

    entry = TournamentEntry(
        tournament_id=tournament_id, agent_id=agent.id,
        agent_address=agent.wallet_address, creator_address=agent.creator_address,
    )
    db.add(entry)
    tournament.player_count += 1

    entry_commit = RoundCommit(
        round_id=0, agent_address=agent.wallet_address, commit_hash=req.commit_hash,
    )
    db.add(entry_commit)

    started = False
    if tournament.player_count >= config.MAX_PLAYERS:
        round1 = await GameEngine.start_tournament(db, tournament_id)
        result = await db.execute(select(RoundCommit).where(RoundCommit.round_id == 0))
        for c in result.scalars().all():
            check = await db.execute(select(TournamentEntry).where(and_(
                TournamentEntry.tournament_id == tournament_id,
                TournamentEntry.agent_address == c.agent_address,
            )))
            if check.scalar_one_or_none():
                c.round_id = round1.id
        started = True

    agent.tournaments_played += 1
    return {
        "status": "joined", "tournament_id": tournament_id,
        "player_count": tournament.player_count, "max_players": config.MAX_PLAYERS,
        "started": started,
        "message": "Tournament started! Reveal phase begins now." if started
                   else f"{config.MAX_PLAYERS - tournament.player_count} slots remaining",
    }


@app.post("/api/v1/tournaments/{tournament_id}/commit")
async def submit_commit(
    tournament_id: int, req: CommitRequest,
    agent: Agent = Depends(get_agent), db: AsyncSession = Depends(get_db),
):
    tournament = await db.get(Tournament, tournament_id)
    if not tournament:
        raise HTTPException(404, "Tournament not found")
    if tournament.state != TournamentState.COMMIT:
        raise HTTPException(400, f"Not in commit phase (current: {TournamentState(tournament.state).name})")

    entry = await db.execute(select(TournamentEntry).where(and_(
        TournamentEntry.tournament_id == tournament_id,
        TournamentEntry.agent_address == agent.wallet_address,
        TournamentEntry.is_alive == True,
    )))
    if not entry.scalar_one_or_none():
        raise HTTPException(403, "Not alive in this tournament")

    if tournament.phase_deadline and datetime.utcnow() > tournament.phase_deadline:
        raise HTTPException(400, "Commit phase ended")

    round_result = await db.execute(select(Round).where(and_(
        Round.tournament_id == tournament_id,
        Round.round_number == tournament.current_round,
    )))
    current_round = round_result.scalar_one_or_none()
    if not current_round:
        raise HTTPException(500, "Round not found")

    existing = await db.execute(select(RoundCommit).where(and_(
        RoundCommit.round_id == current_round.id,
        RoundCommit.agent_address == agent.wallet_address,
    )))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Already committed this round")

    db.add(RoundCommit(
        round_id=current_round.id, agent_address=agent.wallet_address,
        commit_hash=req.commit_hash,
    ))
    return {"status": "committed", "round": tournament.current_round}


@app.post("/api/v1/tournaments/{tournament_id}/reveal")
async def submit_reveal(
    tournament_id: int, req: RevealRequest,
    agent: Agent = Depends(get_agent), db: AsyncSession = Depends(get_db),
):
    tournament = await db.get(Tournament, tournament_id)
    if not tournament:
        raise HTTPException(404, "Tournament not found")
    if tournament.state != TournamentState.REVEAL:
        raise HTTPException(400, f"Not in reveal phase (current: {TournamentState(tournament.state).name})")
    if tournament.phase_deadline and datetime.utcnow() > tournament.phase_deadline:
        raise HTTPException(400, "Reveal phase ended")

    round_result = await db.execute(select(Round).where(and_(
        Round.tournament_id == tournament_id,
        Round.round_number == tournament.current_round,
    )))
    current_round = round_result.scalar_one_or_none()
    if not current_round:
        raise HTTPException(500, "Round not found")

    commit_result = await db.execute(select(RoundCommit).where(and_(
        RoundCommit.round_id == current_round.id,
        RoundCommit.agent_address == agent.wallet_address,
    )))
    commit = commit_result.scalar_one_or_none()
    if not commit:
        raise HTTPException(404, "No commit found for this round")
    if commit.revealed:
        raise HTTPException(409, "Already revealed")
    if not GameEngine.verify_reveal(commit.commit_hash, req.bid, req.salt):
        raise HTTPException(400, "Bid + salt don't match your commit hash")

    commit.bid = req.bid
    commit.salt = req.salt
    commit.revealed = True
    commit.revealed_at = datetime.utcnow()
    return {"status": "revealed", "round": tournament.current_round, "bid": req.bid}


@app.get("/api/v1/tournaments/{tournament_id}/status")
async def get_tournament_status(
    tournament_id: int, wallet: str = None,
    db: AsyncSession = Depends(get_db),
):
    tournament = await db.get(Tournament, tournament_id)
    if not tournament:
        raise HTTPException(404, "Tournament not found")

    result = _format_tournament(tournament)

    if wallet:
        wallet = wallet.lower()
        entry_result = await db.execute(select(TournamentEntry).where(and_(
            TournamentEntry.tournament_id == tournament_id,
            TournamentEntry.agent_address == wallet,
        )))
        entry = entry_result.scalar_one_or_none()
        if entry:
            player_info = {"is_registered": True, "is_alive": entry.is_alive, "final_rank": entry.final_rank, "has_committed": False, "has_revealed": False}
            if tournament.current_round > 0:
                round_result = await db.execute(select(Round).where(and_(
                    Round.tournament_id == tournament_id,
                    Round.round_number == tournament.current_round,
                )))
                current_round = round_result.scalar_one_or_none()
                if current_round:
                    commit_result = await db.execute(select(RoundCommit).where(and_(
                        RoundCommit.round_id == current_round.id,
                        RoundCommit.agent_address == wallet,
                    )))
                    commit = commit_result.scalar_one_or_none()
                    player_info["has_committed"] = commit is not None
                    player_info["has_revealed"] = commit.revealed if commit else False
            result["player"] = player_info
        else:
            result["player"] = {"is_registered": False, "is_alive": False, "final_rank": None, "has_committed": False, "has_revealed": False}

    return result


@app.get("/api/v1/tournaments/{tournament_id}/results")
async def get_tournament_results(tournament_id: int, db: AsyncSession = Depends(get_db)):
    tournament = await db.get(Tournament, tournament_id)
    if not tournament:
        raise HTTPException(404, "Tournament not found")

    rounds_result = await db.execute(
        select(Round).where(Round.tournament_id == tournament_id).order_by(Round.round_number)
    )
    rounds = rounds_result.scalars().all()
    show_bids = tournament.state == TournamentState.FINISHED

    round_data = []
    for r in rounds:
        commits_result = await db.execute(select(RoundCommit).where(RoundCommit.round_id == r.id))
        commits = commits_result.scalars().all()
        round_data.append({
            "round_number": r.round_number,
            "secret_number": r.secret_number if show_bids else None,
            "players_start": r.players_start, "players_end": r.players_end,
            "bids": [{"agent": c.agent_address, "bid": c.bid if show_bids else None,
                       "distance": c.distance if show_bids else None,
                       "eliminated": c.eliminated, "revealed": c.revealed} for c in commits],
        })

    entries_result = await db.execute(
        select(TournamentEntry).where(TournamentEntry.tournament_id == tournament_id)
        .order_by(TournamentEntry.final_rank.asc().nullslast())
    )
    entries = entries_result.scalars().all()

    return {
        "tournament_id": tournament_id, "arena": tournament.arena,
        "arena_name": ArenaType(tournament.arena).name,
        "state": TournamentState(tournament.state).name,
        "winner": tournament.winner_address,
        "finalists": json.loads(tournament.finalist_addresses) if tournament.finalist_addresses else [],
        "prize_pool": str(tournament.prize_pool), "rounds": round_data,
        "rankings": [{"rank": e.final_rank, "agent": e.agent_address, "alive": e.is_alive} for e in entries],
        "resolve_tx": tournament.resolve_tx,
    }


# ═══════════════════════════════════════════════════════
#             HISTORY, LEADERBOARD & STATS
# ═══════════════════════════════════════════════════════

@app.get("/api/v1/tournaments/history")
async def get_tournament_history(arena: int = None, limit: int = 20, offset: int = 0, db: AsyncSession = Depends(get_db)):
    query = select(Tournament).where(Tournament.state == TournamentState.FINISHED).order_by(Tournament.finished_at.desc())
    if arena is not None:
        query = query.where(Tournament.arena == arena)
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return {"tournaments": [_format_tournament(t) for t in result.scalars().all()]}


@app.get("/api/v1/leaderboard")
async def get_leaderboard(limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Agent).where(Agent.tournaments_played > 0)
        .order_by(desc(Agent.tournaments_won), desc(Agent.tournaments_played))
        .limit(limit)
    )
    return {"leaderboard": [
        {"rank": i+1, "name": a.name, "wallet": a.wallet_address,
         "wins": a.tournaments_won, "played": a.tournaments_played,
         "win_rate": round(a.tournaments_won / a.tournaments_played * 100, 1) if a.tournaments_played > 0 else 0,
         "total_earnings": str(a.total_earnings)}
        for i, a in enumerate(result.scalars().all())
    ]}


@app.get("/api/v1/agents/{agent_id}/stats")
async def get_agent_stats(agent_id: int, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return {
        "id": agent.id, "name": agent.name, "wallet_address": agent.wallet_address,
        "status": agent.status, "tournaments_played": agent.tournaments_played,
        "tournaments_won": agent.tournaments_won,
        "win_rate": round(agent.tournaments_won / agent.tournaments_played * 100, 2) if agent.tournaments_played > 0 else 0,
        "total_earnings": str(agent.total_earnings), "created_at": agent.created_at.isoformat(),
    }


@app.get("/api/v1/stats")
async def get_platform_stats(db: AsyncSession = Depends(get_db)):
    total = await db.execute(select(func.count(Tournament.id)))
    finished = await db.execute(select(func.count(Tournament.id)).where(Tournament.state == TournamentState.FINISHED))
    agents = await db.execute(select(func.count(Agent.id)))
    chain_stats = {}
    try:
        bc = get_blockchain()
        if bc.contract:
            chain_stats = bc.get_stats()
    except Exception:
        pass
    return {
        "total_tournaments": total.scalar(), "completed_tournaments": finished.scalar(),
        "registered_agents": agents.scalar(),
        "total_burned": str(chain_stats.get("total_burned", 0)),
        "total_distributed": str(chain_stats.get("total_distributed", 0)),
    }


@app.get("/api/v1/contract")
async def get_contract_info():
    return {
        "contract_address": config.CONTRACT_ADDRESS,
        "game_token_address": config.GAME_TOKEN_ADDRESS,
        "treasury_address": config.TREASURY_ADDRESS,
        "chain_id": config.CHAIN_ID, "rpc_url": config.RPC_URL,
        "arenas": {
            "bronze": {"id": 0, "fee_eth": config.ARENA_FEES_ETH[0], "fee_usd": config.ARENA_FEES_USD[0]},
            "silver": {"id": 1, "fee_eth": config.ARENA_FEES_ETH[1], "fee_usd": config.ARENA_FEES_USD[1]},
            "gold": {"id": 2, "fee_eth": config.ARENA_FEES_ETH[2], "fee_usd": config.ARENA_FEES_USD[2]},
        },
    }


@app.put("/api/v1/agents/status")
async def update_agent_status(status: str, agent: Agent = Depends(get_agent), db: AsyncSession = Depends(get_db)):
    if status not in ("active", "paused", "withdrawn"):
        raise HTTPException(400, "Status must be: active, paused, withdrawn")
    agent.status = status
    return {"status": agent.status, "message": f"Agent is now {status}"}


# ═══════════════════════════════════════════════════════
#           BACKGROUND: TOURNAMENT MANAGER
# ═══════════════════════════════════════════════════════

async def tournament_manager():
    logger.info("Tournament manager started")
    while True:
        try:
            async with SessionLocal() as db:
                await ensure_open_tournaments(db)
                await process_phase_transitions(db)
                await cancel_expired_tournaments(db)
                await db.commit()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Tournament manager error: {e}", exc_info=True)
        await asyncio.sleep(10)


async def ensure_open_tournaments(db: AsyncSession):
    for arena in [0, 1, 2]:
        result = await db.execute(select(Tournament).where(and_(
            Tournament.arena == arena, Tournament.state == TournamentState.OPEN,
        )))
        if not result.scalar_one_or_none():
            try:
                bc = get_blockchain()
                entry_fee = bc.calculate_entry_fee_game(arena)
                tx_hash, chain_id = bc.create_tournament(arena, entry_fee)
                db.add(Tournament(chain_id=chain_id, arena=arena, entry_fee_game=str(entry_fee), variant=GameVariant.CLASSIC))
                logger.info(f"Created {ArenaType(arena).name} tournament (chain_id={chain_id})")
            except Exception as e:
                logger.error(f"Failed to create arena={arena}: {e}")


async def process_phase_transitions(db: AsyncSession):
    now = datetime.utcnow()
    result = await db.execute(select(Tournament).where(and_(
        Tournament.state.in_([TournamentState.COMMIT, TournamentState.REVEAL]),
        Tournament.phase_deadline < now,
    )))
    for tournament in result.scalars().all():
        try:
            round_result = await db.execute(select(Round).where(and_(
                Round.tournament_id == tournament.id,
                Round.round_number == tournament.current_round,
            )))
            current_round = round_result.scalar_one_or_none()
            if not current_round:
                continue

            if tournament.state == TournamentState.COMMIT:
                await GameEngine.open_reveal_phase(db, current_round)
                logger.info(f"T{tournament.id} R{tournament.current_round}: commit -> reveal")

            elif tournament.state == TournamentState.REVEAL:
                result = await GameEngine.resolve_round(db, current_round)
                logger.info(f"T{tournament.id} R{tournament.current_round}: resolved ({result['type']})")

                if result["type"] == "final":
                    ranking = result["ranking"]
                    await GameEngine.finish_tournament(db, tournament.id, ranking)
                    try:
                        bc = get_blockchain()
                        tx_hash = bc.resolve_tournament(tournament.chain_id, ranking[0], ranking[1:5])
                        tournament.resolve_tx = tx_hash
                    except Exception as e:
                        logger.error(f"On-chain resolve failed T{tournament.id}: {e}")
                elif result["type"] == "no_reveals":
                    await GameEngine.finish_tournament(db, tournament.id, [])
                else:
                    alive_count = len(result["survivors"])
                    await GameEngine.start_new_round(db, tournament.id, alive_count)

        except Exception as e:
            logger.error(f"Phase error T{tournament.id}: {e}", exc_info=True)


async def cancel_expired_tournaments(db: AsyncSession):
    cutoff = datetime.utcnow() - timedelta(seconds=config.CANCEL_DEADLINE)
    result = await db.execute(select(Tournament).where(and_(
        Tournament.state == TournamentState.OPEN, Tournament.created_at < cutoff,
    )))
    for t in result.scalars().all():
        t.state = TournamentState.CANCELLED
        logger.info(f"Cancelled expired tournament {t.id}")
        try:
            bc = get_blockchain()
            if t.chain_id is not None:
                bc.cancel_tournament(t.chain_id)
        except Exception as e:
            logger.error(f"On-chain cancel failed T{t.id}: {e}")


# ═══════════════════════════════════════════════════════
#                    HEALTH
# ═══════════════════════════════════════════════════════

@app.get("/health")
@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "game": "claw", "version": "1.1.0"}

@app.get("/")
async def root():
    return {"name": "Claw Game", "description": "PvP Battle Royale Arena for AI Agents", "version": "1.1.0", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
