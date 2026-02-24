"""
Claw Game — Database Models
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, Text, BigInteger, Enum as SAEnum
)
from sqlalchemy.orm import relationship, declarative_base
import enum

Base = declarative_base()


class ArenaType(enum.IntEnum):
    BRONZE = 0
    SILVER = 1
    GOLD = 2


class TournamentState(enum.IntEnum):
    OPEN = 0          # Waiting for 100 players
    ACTIVE = 1        # Game in progress
    COMMIT = 2        # Waiting for commits (round > 1)
    REVEAL = 3        # Waiting for reveals
    RESOLVING = 4     # Computing elimination
    FINISHED = 5      # Prizes distributed
    CANCELLED = 6     # Timeout, refunds available


class GameVariant(enum.IntEnum):
    CLASSIC = 0       # Closest to secret wins
    INVERSE = 1       # Furthest from secret wins
    RANGE = 2         # Guess 50-number range


# ═══════════════════════════════════════════
#                 AGENTS
# ═══════════════════════════════════════════

class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet_address = Column(String(42), unique=True, nullable=False, index=True)
    creator_address = Column(String(42), nullable=False)
    name = Column(String(100), default="")
    api_key = Column(String(64), unique=True, nullable=False)
    status = Column(String(20), default="active")  # active, paused, withdrawn
    created_at = Column(DateTime, default=datetime.utcnow)

    # Stats
    tournaments_played = Column(Integer, default=0)
    tournaments_won = Column(Integer, default=0)
    total_earnings = Column(String, default="0")  # in $GAME wei

    entries = relationship("TournamentEntry", back_populates="agent")


# ═══════════════════════════════════════════
#              TOURNAMENTS
# ═══════════════════════════════════════════

class Tournament(Base):
    __tablename__ = "tournaments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chain_id = Column(Integer, nullable=True)  # On-chain tournament ID
    arena = Column(Integer, nullable=False)     # 0=Bronze, 1=Silver, 2=Gold
    state = Column(Integer, default=TournamentState.OPEN)
    variant = Column(Integer, default=GameVariant.CLASSIC)
    entry_fee_game = Column(String, nullable=False)  # $GAME amount (wei)

    player_count = Column(Integer, default=0)
    current_round = Column(Integer, default=0)
    prize_pool = Column(String, default="0")

    # Results
    winner_address = Column(String(42), nullable=True)
    finalist_addresses = Column(Text, nullable=True)  # JSON array

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    phase_deadline = Column(DateTime, nullable=True)

    # On-chain tx
    resolve_tx = Column(String(66), nullable=True)

    entries = relationship("TournamentEntry", back_populates="tournament")
    rounds = relationship("Round", back_populates="tournament")


# ═══════════════════════════════════════════
#           TOURNAMENT ENTRIES
# ═══════════════════════════════════════════

class TournamentEntry(Base):
    __tablename__ = "tournament_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    agent_address = Column(String(42), nullable=False)
    creator_address = Column(String(42), nullable=False)

    is_alive = Column(Boolean, default=True)  # Still in tournament
    final_rank = Column(Integer, nullable=True)
    prize_amount = Column(String, default="0")

    joined_at = Column(DateTime, default=datetime.utcnow)

    tournament = relationship("Tournament", back_populates="entries")
    agent = relationship("Agent", back_populates="entries")


# ═══════════════════════════════════════════
#                 ROUNDS
# ═══════════════════════════════════════════

class Round(Base):
    __tablename__ = "rounds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False)
    round_number = Column(Integer, nullable=False)

    secret_number = Column(Integer, nullable=True)   # 1-1000
    players_start = Column(Integer, default=0)       # Alive at start
    players_end = Column(Integer, default=0)         # Alive at end
    commit_deadline = Column(DateTime, nullable=True)
    reveal_deadline = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    tournament = relationship("Tournament", back_populates="rounds")
    commits = relationship("RoundCommit", back_populates="round")


# ═══════════════════════════════════════════
#              ROUND COMMITS
# ═══════════════════════════════════════════

class RoundCommit(Base):
    __tablename__ = "round_commits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    round_id = Column(Integer, ForeignKey("rounds.id"), nullable=False)
    agent_address = Column(String(42), nullable=False)

    commit_hash = Column(String(66), nullable=False)  # keccak256(bid + salt)
    bid = Column(Integer, nullable=True)              # Revealed bid (1-1000)
    salt = Column(String(66), nullable=True)          # Revealed salt
    revealed = Column(Boolean, default=False)
    eliminated = Column(Boolean, default=False)
    distance = Column(Integer, nullable=True)          # Distance to secret

    committed_at = Column(DateTime, default=datetime.utcnow)
    revealed_at = Column(DateTime, nullable=True)

    round = relationship("Round", back_populates="commits")
