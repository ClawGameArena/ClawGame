from dotenv import load_dotenv
load_dotenv()

"""
Claw Game — Configuration
All env vars match the .env file exactly.
"""
import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # ── Server ──
    HOST: str = os.getenv("API_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("API_PORT", "8000"))

    # ── Database ──
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./clawgame.db")

    # ── Blockchain (.env names match exactly) ──
    RPC_URL: str = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
    CHAIN_ID: int = int(os.getenv("CHAIN_ID", "8453"))
    CONTRACT_ADDRESS: str = os.getenv("CONTRACT_ADDRESS", "")
    GAME_TOKEN_ADDRESS: str = os.getenv("GAME_TOKEN_ADDRESS", "")
    TREASURY_ADDRESS: str = os.getenv("TREASURY_WALLET", "")

    # Private key: handle with or without 0x
    OWNER_PRIVATE_KEY: str = ""

    # ── Game Settings ──
    MAX_PLAYERS: int = 25
    BID_MIN: int = 1
    BID_MAX: int = 1000
    COMMIT_DURATION: int = 300      # 5 minutes
    REVEAL_DURATION: int = 300      # 5 minutes
    RESOLUTION_PAUSE: int = 30      # 30 seconds between rounds
    CANCEL_DEADLINE: int = 7 * 86400  # 7 days

    # ── Rate Limiting ──
    RATE_LIMIT_PER_MINUTE: int = 30  # max requests per IP per minute

    # ── Entry Fees (ETH) — used to calculate $GAME amount ──
    ARENA_FEES_ETH: dict = field(default_factory=dict)
    ARENA_FEES_USD: dict = field(default_factory=dict)

    def __post_init__(self):
        # Handle PRIVATE_KEY with or without 0x
        pk = os.getenv("PRIVATE_KEY", "")
        if pk and not pk.startswith("0x"):
            pk = "0x" + pk
        self.OWNER_PRIVATE_KEY = pk

        self.ARENA_FEES_ETH = {
            0: 0.002,   # Bronze ~$5
            1: 0.02,    # Silver ~$50
            2: 0.2,     # Gold   ~$500
        }
        self.ARENA_FEES_USD = {
            0: 5,
            1: 50,
            2: 500,
        }


config = Config()
