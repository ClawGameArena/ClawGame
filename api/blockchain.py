"""
Claw Game — Blockchain Interaction v2
Handles all Web3 calls to the ClawGame smart contract on Base.

Fixes from audit:
- resolve() now takes finalistCount param
- Proper finalist padding (address(0) for empty slots)
- recoverDust limited by contract
- Pause support
"""
import json
import logging
from web3 import Web3
from web3.middleware import geth_poa_middleware
from config import config

logger = logging.getLogger(__name__)

CONTRACT_ABI = json.loads("""[
    {
        "inputs": [{"type": "uint8"}, {"type": "uint96"}],
        "name": "createTournament",
        "outputs": [{"type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"type": "uint256", "name": "tid"},
            {"type": "address", "name": "winner"},
            {"type": "address[4]", "name": "finalists"},
            {"type": "uint8", "name": "finalistCount"}
        ],
        "name": "resolve",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"type": "uint256"}],
        "name": "cancel",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"type": "uint256"}],
        "name": "getTournament",
        "outputs": [
            {"type": "uint8"}, {"type": "uint8"}, {"type": "uint96"},
            {"type": "uint256"}, {"type": "uint32"}, {"type": "uint40"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "getStats",
        "outputs": [
            {"type": "uint256"}, {"type": "uint256"},
            {"type": "uint256"}, {"type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "nextTournamentId",
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"type": "uint256"}],
        "name": "getPlayers",
        "outputs": [{"type": "address[]"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"type": "uint256"}, {"type": "address"}],
        "name": "isPlayer",
        "outputs": [{"type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"type": "bool"}],
        "name": "setPaused",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "paused",
        "outputs": [{"type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    }
]""")

ZERO_ADDR = "0x0000000000000000000000000000000000000000"


class Blockchain:

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(config.RPC_URL))
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)

        if config.OWNER_PRIVATE_KEY:
            self.account = self.w3.eth.account.from_key(config.OWNER_PRIVATE_KEY)
        else:
            self.account = None
            logger.warning("No PRIVATE_KEY — read-only mode")

        if config.CONTRACT_ADDRESS:
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(config.CONTRACT_ADDRESS),
                abi=CONTRACT_ABI,
            )
        else:
            self.contract = None
            logger.warning("No CONTRACT_ADDRESS — contract calls disabled")

    def _send_tx(self, fn, value=0) -> str:
        if not self.account:
            raise Exception("No private key configured")
        tx = fn.build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gas": 500_000,
            "gasPrice": self.w3.eth.gas_price,
            "chainId": config.CHAIN_ID,
            "value": value,
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt["status"] != 1:
            raise Exception(f"Transaction reverted: {tx_hash.hex()}")
        logger.info(f"TX confirmed: {tx_hash.hex()}")
        return tx_hash.hex()

    # ───────── Tournament ─────────

    def create_tournament(self, arena: int, entry_fee_wei: int) -> tuple[str, int]:
        fn = self.contract.functions.createTournament(arena, entry_fee_wei)
        tx_hash = self._send_tx(fn)
        on_chain_id = self.contract.functions.nextTournamentId().call() - 1
        return tx_hash, on_chain_id

    def resolve_tournament(self, tournament_id: int, winner: str, finalists: list[str]) -> str:
        """
        Resolve tournament on-chain.
        Handles variable finalist count properly:
        - Passes actual finalistCount to contract
        - Pads with address(0) for empty slots (contract skips them)
        """
        real_finalists = [f for f in finalists[:4] if f and f != ZERO_ADDR]
        finalist_count = len(real_finalists)

        # Pad to exactly 4 addresses
        padded = list(real_finalists)
        while len(padded) < 4:
            padded.append(ZERO_ADDR)

        fn = self.contract.functions.resolve(
            tournament_id,
            Web3.to_checksum_address(winner),
            [Web3.to_checksum_address(f) for f in padded],
            finalist_count,
        )
        return self._send_tx(fn)

    def cancel_tournament(self, tournament_id: int) -> str:
        fn = self.contract.functions.cancel(tournament_id)
        return self._send_tx(fn)

    def set_paused(self, is_paused: bool) -> str:
        fn = self.contract.functions.setPaused(is_paused)
        return self._send_tx(fn)

    # ───────── Verification ─────────

    def verify_player_joined(self, tournament_id: int, player_address: str) -> bool:
        if not self.contract:
            return False
        try:
            return self.contract.functions.isPlayer(
                tournament_id,
                Web3.to_checksum_address(player_address)
            ).call()
        except Exception as e:
            logger.error(f"On-chain verify failed: {e}")
            return False

    # ───────── Views ─────────

    def get_tournament(self, tournament_id: int) -> dict:
        r = self.contract.functions.getTournament(tournament_id).call()
        return {"arena": r[0], "state": r[1], "entry_fee": r[2],
                "prize_pool": r[3], "player_count": r[4], "created_at": r[5]}

    def get_stats(self) -> dict:
        r = self.contract.functions.getStats().call()
        return {"total_burned": r[0], "total_distributed": r[1],
                "total_completed": r[2], "next_tournament_id": r[3]}

    def is_paused(self) -> bool:
        if not self.contract:
            return False
        return self.contract.functions.paused().call()

    def calculate_entry_fee_game(self, arena: int) -> int:
        eth_fee = config.ARENA_FEES_ETH.get(arena, 0.002)
        game_price = self.get_game_price_in_eth()
        if game_price <= 0:
            raise ValueError("Invalid $GAME price")
        game_amount = eth_fee / game_price
        return int(game_amount * (10 ** 18))

    def get_game_price_in_eth(self) -> float:
        import os
        return float(os.getenv("GAME_PRICE_ETH", "0.000002"))


blockchain: Blockchain | None = None

def get_blockchain() -> Blockchain:
    global blockchain
    if blockchain is None:
        blockchain = Blockchain()
    return blockchain
