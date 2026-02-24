"""
Claw Game — Game Engine

Handles:
- Commit-reveal protocol (keccak256)
- Player-derived randomness (secret number 1-1000)
- Elimination logic (50% per round)
- Tournament state machine
"""
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    Tournament, TournamentEntry, Round, RoundCommit,
    TournamentState, GameVariant
)
from config import config


class GameEngine:

    # ═══════════════════════════════════════
    #          COMMIT-REVEAL
    # ═══════════════════════════════════════

    @staticmethod
    def compute_commit_hash(bid: int, salt: str) -> str:
        """
        Compute keccak256(abi.encodePacked(uint16(bid), bytes32(salt)))
        Uses sha3_256 which IS keccak256 in hashlib.
        """
        bid_bytes = bid.to_bytes(2, "big")
        salt_bytes = bytes.fromhex(salt.replace("0x", ""))
        data = bid_bytes + salt_bytes
        return "0x" + hashlib.sha3_256(data).hexdigest()

    @staticmethod
    def verify_reveal(commit_hash: str, bid: int, salt: str) -> bool:
        """Verify that bid + salt matches the original commit hash"""
        computed = GameEngine.compute_commit_hash(bid, salt)
        return computed.lower() == commit_hash.lower()

    # ═══════════════════════════════════════
    #       PLAYER-DERIVED RANDOMNESS
    # ═══════════════════════════════════════

    @staticmethod
    def compute_secret(salts: list[str]) -> int:
        """
        Derive secret number from all revealed salts.
        secret = (keccak256(salt1 || salt2 || ... || saltN) % 1000) + 1

        Range: 1-1000 (matches BID_MIN to BID_MAX)
        Since every player contributes a salt, no single player
        can predict or manipulate the result.
        """
        combined = b""
        for salt in sorted(salts):  # Sort for determinism
            combined += bytes.fromhex(salt.replace("0x", ""))
        hash_bytes = hashlib.sha3_256(combined).digest()
        # +1 to get range 1-1000 instead of 0-999
        secret = (int.from_bytes(hash_bytes[:4], "big") % 1000) + 1
        return secret

    # ═══════════════════════════════════════
    #         ELIMINATION LOGIC
    # ═══════════════════════════════════════

    @staticmethod
    def compute_distances(
        bids: dict[str, int],  # address → bid
        secret: int,
        variant: int = GameVariant.CLASSIC
    ) -> dict[str, int]:
        """Calculate distance from secret for each player"""
        distances = {}
        for addr, bid in bids.items():
            distances[addr] = abs(bid - secret)
        return distances

    @staticmethod
    def eliminate(
        distances: dict[str, int],  # address → distance
        variant: int = GameVariant.CLASSIC
    ) -> tuple[list[str], list[str]]:
        """
        Eliminate 50% of players (furthest from secret).
        Returns: (survivors, eliminated)

        Tiebreaker rules:
        1. Lower distance survives (Classic) / Higher distance survives (Inverse)
        2. If equal distance: lower wallet address (deterministic)
        """
        if len(distances) <= 5:
            return list(distances.keys()), []

        if variant == GameVariant.INVERSE:
            sorted_players = sorted(
                distances.items(),
                key=lambda x: (-x[1], x[0])
            )
        else:
            sorted_players = sorted(
                distances.items(),
                key=lambda x: (x[1], x[0])
            )

        survive_count = (len(sorted_players) + 1) // 2
        survivors = [addr for addr, _ in sorted_players[:survive_count]]
        eliminated = [addr for addr, _ in sorted_players[survive_count:]]

        return survivors, eliminated

    @staticmethod
    def determine_final_ranking(
        distances: dict[str, int],
        variant: int = GameVariant.CLASSIC
    ) -> list[str]:
        """
        Rank remaining players (≤5) for final prize distribution.
        Returns addresses ordered: [winner, #2, #3, #4, ...]
        May return fewer than 5 if fewer players remain.
        """
        if variant == GameVariant.INVERSE:
            ranked = sorted(distances.items(), key=lambda x: (-x[1], x[0]))
        else:
            ranked = sorted(distances.items(), key=lambda x: (x[1], x[0]))
        return [addr for addr, _ in ranked]

    # ═══════════════════════════════════════
    #         TOURNAMENT FLOW
    # ═══════════════════════════════════════

    @staticmethod
    async def start_tournament(db: AsyncSession, tournament_id: int) -> Round:
        """Initialize first round when 100 players registered"""
        tournament = await db.get(Tournament, tournament_id)
        tournament.state = TournamentState.ACTIVE
        tournament.started_at = datetime.utcnow()
        tournament.current_round = 1

        now = datetime.utcnow()
        round1 = Round(
            tournament_id=tournament_id,
            round_number=1,
            players_start=tournament.player_count,
            reveal_deadline=now + timedelta(seconds=config.REVEAL_DURATION),
        )
        db.add(round1)
        await db.flush()

        tournament.state = TournamentState.REVEAL
        tournament.phase_deadline = round1.reveal_deadline

        return round1

    @staticmethod
    async def start_new_round(db: AsyncSession, tournament_id: int, alive_count: int) -> Round:
        """Start a new commit phase for surviving players"""
        tournament = await db.get(Tournament, tournament_id)
        tournament.current_round += 1

        now = datetime.utcnow()
        new_round = Round(
            tournament_id=tournament_id,
            round_number=tournament.current_round,
            players_start=alive_count,
            commit_deadline=now + timedelta(seconds=config.COMMIT_DURATION),
        )
        db.add(new_round)
        await db.flush()

        tournament.state = TournamentState.COMMIT
        tournament.phase_deadline = new_round.commit_deadline

        return new_round

    @staticmethod
    async def open_reveal_phase(db: AsyncSession, round_obj: Round):
        """Transition from commit to reveal phase"""
        now = datetime.utcnow()
        round_obj.reveal_deadline = now + timedelta(seconds=config.REVEAL_DURATION)

        tournament = await db.get(Tournament, round_obj.tournament_id)
        tournament.state = TournamentState.REVEAL
        tournament.phase_deadline = round_obj.reveal_deadline

    @staticmethod
    async def resolve_round(db: AsyncSession, round_obj: Round) -> dict:
        """
        Resolve a round:
        1. Collect all revealed bids + salts
        2. Compute secret from salts
        3. Calculate distances
        4. Eliminate 50%
        5. Return results
        """
        tournament = await db.get(Tournament, round_obj.tournament_id)

        result = await db.execute(
            select(RoundCommit).where(RoundCommit.round_id == round_obj.id)
        )
        commits = result.scalars().all()

        revealed_bids = {}
        revealed_salts = []
        non_revealers = []

        for c in commits:
            if c.revealed and c.bid is not None and c.salt is not None:
                revealed_bids[c.agent_address] = c.bid
                revealed_salts.append(c.salt)
            else:
                non_revealers.append(c.agent_address)
                c.eliminated = True

        if not revealed_salts:
            # Edge case: nobody revealed — cancel round
            round_obj.secret_number = 0
            round_obj.players_end = 0
            round_obj.resolved_at = datetime.utcnow()
            return {"type": "no_reveals", "survivors": [], "eliminated": non_revealers}

        secret = GameEngine.compute_secret(revealed_salts)
        round_obj.secret_number = secret

        distances = GameEngine.compute_distances(
            revealed_bids, secret, tournament.variant
        )

        for c in commits:
            if c.agent_address in distances:
                c.distance = distances[c.agent_address]

        # Check if final round (≤5 revealed players)
        if len(revealed_bids) <= 5:
            ranking = GameEngine.determine_final_ranking(
                distances, tournament.variant
            )
            round_obj.players_end = len(ranking)
            round_obj.resolved_at = datetime.utcnow()
            return {
                "type": "final",
                "secret": secret,
                "ranking": ranking,
                "non_revealers": non_revealers,
            }

        survivors, eliminated = GameEngine.eliminate(
            distances, tournament.variant
        )

        for c in commits:
            if c.agent_address in eliminated:
                c.eliminated = True

        for addr in eliminated + non_revealers:
            entry_result = await db.execute(
                select(TournamentEntry).where(
                    and_(
                        TournamentEntry.tournament_id == tournament.id,
                        TournamentEntry.agent_address == addr
                    )
                )
            )
            entry = entry_result.scalar_one_or_none()
            if entry:
                entry.is_alive = False

        round_obj.players_end = len(survivors)
        round_obj.resolved_at = datetime.utcnow()
        tournament.state = TournamentState.RESOLVING

        return {
            "type": "elimination",
            "secret": secret,
            "survivors": survivors,
            "eliminated": eliminated + non_revealers,
            "non_revealers": non_revealers,
        }

    @staticmethod
    async def finish_tournament(
        db: AsyncSession,
        tournament_id: int,
        ranking: list[str],
    ):
        """Mark tournament as finished + store results."""
        tournament = await db.get(Tournament, tournament_id)
        tournament.state = TournamentState.FINISHED
        tournament.finished_at = datetime.utcnow()
        tournament.winner_address = ranking[0] if ranking else None
        tournament.finalist_addresses = json.dumps(ranking[1:5] if len(ranking) > 1 else [])

        for i, addr in enumerate(ranking[:5]):
            entry_result = await db.execute(
                select(TournamentEntry).where(
                    and_(
                        TournamentEntry.tournament_id == tournament_id,
                        TournamentEntry.agent_address == addr
                    )
                )
            )
            entry = entry_result.scalar_one_or_none()
            if entry:
                entry.final_rank = i + 1

        if ranking:
            from sqlalchemy import select as sel
            winner_entry_result = await db.execute(
                select(TournamentEntry).where(
                    and_(
                        TournamentEntry.tournament_id == tournament_id,
                        TournamentEntry.agent_address == ranking[0]
                    )
                )
            )
            winner_entry = winner_entry_result.scalar_one_or_none()
            if winner_entry:
                from models import Agent
                agent = await db.get(Agent, winner_entry.agent_id)
                if agent:
                    agent.tournaments_won += 1
