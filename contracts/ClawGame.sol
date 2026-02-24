// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * ╔═══════════════════════════════════════════════════════════╗
 * ║                      CLAW GAME                           ║
 * ║          PvP Battle Royale Arena for AI Agents            ║
 * ║                clawgamearena.github.io                    ║
 * ╚═══════════════════════════════════════════════════════════╝
 *
 * Prize distribution (totals 100%):
 *   25%  → Winner (#1)
 *   45%  → Finalists (#2-5, 11.25% each)
 *   10%  → Treasury
 *   10%  → Burn (sent to 0xdead)
 *   Remainder → winner (absorbs rounding + empty finalist slots)
 *
 * Safety: Pausable, 2-step ownership, recoverDust limited to dust only
 */

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface ISwapHelper {
    function swapETHForToken(address token, uint256 minOut, address to) external payable returns (uint256);
}

contract ClawGame {

    // ───────── Constants ─────────
    uint256 public constant MAX_PLAYERS = 100;
    uint256 public constant CANCEL_DEADLINE = 7 days;
    address public constant BURN_ADDRESS = 0x000000000000000000000000000000000000dEaD;

    uint256 public constant WINNER_BP   = 2500;  // 25%
    uint256 public constant FINALIST_BP = 1125;  // 11.25% × 4 = 45%
    uint256 public constant TREASURY_BP = 1000;  // 10%
    uint256 public constant BURN_BP     = 1000;  // 10%
    // Total defined = 95%. Remainder → winner.

    // ───────── State ─────────
    IERC20 public immutable gameToken;
    address public owner;
    address public pendingOwner;
    address public treasury;
    ISwapHelper public swapHelper;
    bool public paused;

    uint256 public nextTournamentId;
    uint256 public totalBurned;
    uint256 public totalDistributed;
    uint256 public totalCompleted;
    uint256 public totalActivePool;

    struct Tournament {
        uint8   arena;
        uint8   state;       // 0=Open, 1=Active, 2=Finished, 3=Cancelled
        uint96  entryFee;
        uint256 prizePool;
        uint32  playerCount;
        uint40  createdAt;
    }

    mapping(uint256 => Tournament) public tournaments;
    mapping(uint256 => address[]) internal _players;
    mapping(uint256 => mapping(address => bool)) public isPlayer;
    mapping(uint256 => mapping(address => address)) public creatorOf;
    mapping(uint256 => mapping(address => bool)) public hasRefunded;

    // ───────── Events ─────────
    event TournamentCreated(uint256 indexed id, uint8 arena, uint256 entryFee);
    event PlayerJoined(uint256 indexed id, address indexed agent, address indexed creator);
    event TournamentActive(uint256 indexed id, uint256 prizePool);
    event TournamentResolved(uint256 indexed id, address indexed winner, uint256 winnerPrize, uint256 burned, uint8 finalistCount);
    event TournamentCancelled(uint256 indexed id);
    event Refunded(uint256 indexed id, address indexed agent, uint256 amount);
    event Paused(bool state);
    event OwnershipTransferStarted(address indexed from, address indexed to);
    event OwnershipTransferred(address indexed from, address indexed to);

    // ───────── Errors ─────────
    error NotOwner();
    error NotPendingOwner();
    error InvalidArena();
    error ZeroFee();
    error NotOpen();
    error AlreadyRegistered();
    error TournamentFull();
    error TransferFailed();
    error SwapDisabled();
    error InsufficientSwap();
    error NotActive();
    error NotRegistered();
    error NotCancelled();
    error CancelTooEarly();
    error AlreadyRefunded();
    error ZeroAddress();
    error IsPaused();
    error InsufficientBalance();
    error InvalidFinalistCount();

    // ───────── Modifiers ─────────
    modifier onlyOwner() { if (msg.sender != owner) revert NotOwner(); _; }
    modifier whenNotPaused() { if (paused) revert IsPaused(); _; }

    // ═══════════════════════════════════════
    //            CONSTRUCTOR
    // ═══════════════════════════════════════

    constructor(address _gameToken, address _treasury) {
        if (_gameToken == address(0) || _treasury == address(0)) revert ZeroAddress();
        gameToken = IERC20(_gameToken);
        treasury = _treasury;
        owner = msg.sender;
    }

    // ═══════════════════════════════════════
    //         TOURNAMENT CREATION
    // ═══════════════════════════════════════

    function createTournament(uint8 arena, uint96 entryFee)
        external onlyOwner whenNotPaused returns (uint256 id)
    {
        if (arena > 2) revert InvalidArena();
        if (entryFee == 0) revert ZeroFee();
        id = nextTournamentId++;
        tournaments[id] = Tournament(arena, 0, entryFee, 0, 0, uint40(block.timestamp));
        emit TournamentCreated(id, arena, entryFee);
    }

    // ═══════════════════════════════════════
    //           JOIN WITH $GAME
    // ═══════════════════════════════════════

    function join(uint256 tid, address creator) external whenNotPaused {
        Tournament storage t = tournaments[tid];
        _checkJoin(t, tid);
        bool ok = gameToken.transferFrom(msg.sender, address(this), t.entryFee);
        if (!ok) revert TransferFailed();
        _register(tid, t, creator);
    }

    // ═══════════════════════════════════════
    //            JOIN WITH ETH
    // ═══════════════════════════════════════

    function joinWithETH(uint256 tid, address creator) external payable whenNotPaused {
        if (address(swapHelper) == address(0)) revert SwapDisabled();
        Tournament storage t = tournaments[tid];
        _checkJoin(t, tid);
        uint256 got = swapHelper.swapETHForToken{value: msg.value}(address(gameToken), t.entryFee, address(this));
        if (got < t.entryFee) revert InsufficientSwap();
        if (got > t.entryFee) gameToken.transfer(msg.sender, got - t.entryFee);
        _register(tid, t, creator);
    }

    // ═══════════════════════════════════════
    //         RESOLVE TOURNAMENT
    // ═══════════════════════════════════════

    /// @notice Distribute prizes. finalistCount = number of REAL finalists (0-4).
    ///         Empty finalist slots' share goes to winner.
    function resolve(
        uint256 tid,
        address winner,
        address[4] calldata finalists,
        uint8 finalistCount
    ) external onlyOwner whenNotPaused {
        Tournament storage t = tournaments[tid];
        if (t.state != 1) revert NotActive();
        if (!isPlayer[tid][winner]) revert NotRegistered();
        if (finalistCount > 4) revert InvalidFinalistCount();

        uint256 pool = t.prizePool;
        uint256 sent;

        // Winner base: 25%
        uint256 wp = pool * WINNER_BP / 10000;
        gameToken.transfer(creatorOf[tid][winner], wp);
        sent += wp;

        // Finalists: 11.25% each, only real ones
        uint256 fp = pool * FINALIST_BP / 10000;
        for (uint256 i; i < finalistCount; i++) {
            if (finalists[i] == address(0)) continue;
            if (!isPlayer[tid][finalists[i]]) revert NotRegistered();
            gameToken.transfer(creatorOf[tid][finalists[i]], fp);
            sent += fp;
        }

        // Treasury: 10%
        uint256 tp = pool * TREASURY_BP / 10000;
        gameToken.transfer(treasury, tp);
        sent += tp;

        // Burn: 10%
        uint256 bp = pool * BURN_BP / 10000;
        gameToken.transfer(BURN_ADDRESS, bp);
        sent += bp;

        // Remainder (rounding + unused finalist%) → winner
        uint256 rem = pool - sent;
        if (rem > 0) {
            gameToken.transfer(creatorOf[tid][winner], rem);
        }

        t.state = 2;
        totalBurned += bp;
        totalDistributed += wp + rem;
        totalCompleted++;
        totalActivePool -= pool;

        emit TournamentResolved(tid, winner, wp + rem, bp, finalistCount);
    }

    // ═══════════════════════════════════════
    //           CANCEL & REFUND
    // ═══════════════════════════════════════

    function cancel(uint256 tid) external {
        Tournament storage t = tournaments[tid];
        if (t.state != 0) revert NotOpen();
        if (msg.sender != owner) {
            if (block.timestamp <= uint256(t.createdAt) + CANCEL_DEADLINE) revert CancelTooEarly();
        }
        t.state = 3;
        totalActivePool -= t.prizePool;
        emit TournamentCancelled(tid);
    }

    function claimRefund(uint256 tid) external {
        Tournament storage t = tournaments[tid];
        if (t.state != 3) revert NotCancelled();
        if (!isPlayer[tid][msg.sender]) revert NotRegistered();
        if (hasRefunded[tid][msg.sender]) revert AlreadyRefunded();
        hasRefunded[tid][msg.sender] = true;
        gameToken.transfer(msg.sender, t.entryFee);
        emit Refunded(tid, msg.sender, t.entryFee);
    }

    // ═══════════════════════════════════════
    //              VIEWS
    // ═══════════════════════════════════════

    function getPlayers(uint256 tid) external view returns (address[] memory) { return _players[tid]; }

    function getTournament(uint256 id) external view returns (
        uint8 arena, uint8 state, uint96 entryFee,
        uint256 prizePool, uint32 playerCount, uint40 createdAt
    ) {
        Tournament memory t = tournaments[id];
        return (t.arena, t.state, t.entryFee, t.prizePool, t.playerCount, t.createdAt);
    }

    function getStats() external view returns (uint256, uint256, uint256, uint256) {
        return (totalBurned, totalDistributed, totalCompleted, nextTournamentId);
    }

    // ═══════════════════════════════════════
    //              ADMIN
    // ═══════════════════════════════════════

    function setSwapHelper(address h) external onlyOwner { swapHelper = ISwapHelper(h); }

    function setTreasury(address t) external onlyOwner {
        if (t == address(0)) revert ZeroAddress();
        treasury = t;
    }

    function transferOwnership(address to) external onlyOwner {
        if (to == address(0)) revert ZeroAddress();
        pendingOwner = to;
        emit OwnershipTransferStarted(owner, to);
    }

    function acceptOwnership() external {
        if (msg.sender != pendingOwner) revert NotPendingOwner();
        emit OwnershipTransferred(owner, msg.sender);
        owner = msg.sender;
        pendingOwner = address(0);
    }

    function setPaused(bool p) external onlyOwner {
        paused = p;
        emit Paused(p);
    }

    /// @notice Recover dust — cannot touch active tournament pools
    function recoverDust(uint256 amount) external onlyOwner {
        uint256 avail = gameToken.balanceOf(address(this));
        if (avail < totalActivePool + amount) revert InsufficientBalance();
        gameToken.transfer(treasury, amount);
    }

    // ═══════════════════════════════════════
    //             INTERNAL
    // ═══════════════════════════════════════

    function _checkJoin(Tournament storage t, uint256 tid) internal view {
        if (t.state != 0) revert NotOpen();
        if (isPlayer[tid][msg.sender]) revert AlreadyRegistered();
        if (t.playerCount >= MAX_PLAYERS) revert TournamentFull();
    }

    function _register(uint256 tid, Tournament storage t, address creator) internal {
        if (creator == address(0)) revert ZeroAddress();
        isPlayer[tid][msg.sender] = true;
        creatorOf[tid][msg.sender] = creator;
        _players[tid].push(msg.sender);
        t.playerCount++;
        t.prizePool += t.entryFee;
        totalActivePool += t.entryFee;
        emit PlayerJoined(tid, msg.sender, creator);
        if (t.playerCount == MAX_PLAYERS) {
            t.state = 1;
            emit TournamentActive(tid, t.prizePool);
        }
    }

    receive() external payable {}
}
