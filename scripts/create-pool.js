const { ethers } = require("hardhat");

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

const ROUTER_ABI = [
  "function addLiquidityETH(address token, uint amountTokenDesired, uint amountTokenMin, uint amountETHMin, address to, uint deadline) external payable returns (uint amountToken, uint amountETH, uint liquidity)",
  "function factory() external view returns (address)"
];

const FACTORY_ABI = [
  "function getPair(address tokenA, address tokenB) external view returns (address pair)"
];

const PAIR_ABI = [
  "function getReserves() external view returns (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast)",
  "function token0() external view returns (address)",
  "function token1() external view returns (address)",
  "function totalSupply() external view returns (uint256)",
  "function balanceOf(address owner) external view returns (uint256)"
];

async function main() {
  const [deployer] = await ethers.getSigners();
  const GAME_TOKEN = "0x4d442EC52ce06e7CcD3E88622782736f62DC3843";
  const ROUTER     = "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24";
  const WETH       = "0x4200000000000000000000000000000000000006"; // WETH on Base

  const TOKEN_AMOUNT = ethers.parseEther("400000000");  // 400M $GAME
  const ETH_AMOUNT   = ethers.parseEther("0.008");      // 0.008 ETH

  console.log("=".repeat(60));
  console.log("  CLAW GAME — CREATE UNISWAP V2 POOL");
  console.log("=".repeat(60));
  console.log("Deployer     :", deployer.address);
  console.log("GameToken    :", GAME_TOKEN);
  console.log("Router V2    :", ROUTER);
  console.log("Token amount : 400,000,000 $GAME");
  console.log("ETH amount   : 0.008 ETH");

  const ethBal = await ethers.provider.getBalance(deployer.address);
  console.log("ETH balance  :", ethers.formatEther(ethBal), "ETH");

  const token = await ethers.getContractAt("GameToken", GAME_TOKEN);
  const gameBal = await token.balanceOf(deployer.address);
  console.log("$GAME balance:", ethers.formatEther(gameBal));
  console.log("=".repeat(60));

  if (ethBal < ETH_AMOUNT) {
    console.log("ERROR: Not enough ETH for liquidity + gas");
    process.exit(1);
  }
  if (gameBal < TOKEN_AMOUNT) {
    console.log("ERROR: Not enough $GAME tokens");
    process.exit(1);
  }

  // ════════════════════════════════════════════
  //  STEP 1 — Approve Router
  // ════════════════════════════════════════════
  console.log("\n[1/2] Approving Router to spend 400M $GAME...");
  const approveTx = await token.approve(ROUTER, TOKEN_AMOUNT);
  console.log("  tx hash:", approveTx.hash);
  await approveTx.wait();
  console.log("  Approve confirmed");

  console.log("  Waiting 10s...");
  await sleep(10000);

  // ════════════════════════════════════════════
  //  STEP 2 — Add Liquidity ETH
  // ════════════════════════════════════════════
  const router = new ethers.Contract(ROUTER, ROUTER_ABI, deployer);
  const deadline = Math.floor(Date.now() / 1000) + 1800; // now + 30 min

  console.log("\n[2/2] Adding liquidity: 400M $GAME + 0.008 ETH...");
  const addTx = await router.addLiquidityETH(
    GAME_TOKEN,
    TOKEN_AMOUNT,       // amountTokenDesired
    TOKEN_AMOUNT,       // amountTokenMin (400M exact)
    0,                  // amountETHMin
    deployer.address,   // LP tokens to deployer
    deadline,
    { value: ETH_AMOUNT }
  );
  console.log("  tx hash:", addTx.hash);
  console.log("  Waiting for confirmation...");
  const receipt = await addTx.wait();
  console.log("  Liquidity added! Gas used:", receipt.gasUsed.toString());

  await sleep(5000);

  // ════════════════════════════════════════════
  //  VERIFY POOL
  // ════════════════════════════════════════════
  console.log("\n  Verifying pool...");
  const factory = new ethers.Contract(await router.factory(), FACTORY_ABI, deployer);
  const pairAddress = await factory.getPair(GAME_TOKEN, WETH);
  console.log("  Pair address:", pairAddress);

  const pair = new ethers.Contract(pairAddress, PAIR_ABI, deployer);
  const [reserve0, reserve1] = await pair.getReserves();
  const token0 = await pair.token0();
  const lpBalance = await pair.balanceOf(deployer.address);
  const lpTotal   = await pair.totalSupply();

  const isToken0Game = token0.toLowerCase() === GAME_TOKEN.toLowerCase();
  const gameReserve = isToken0Game ? reserve0 : reserve1;
  const ethReserve  = isToken0Game ? reserve1 : reserve0;

  console.log("\n" + "=".repeat(60));
  console.log("  POOL CREATED");
  console.log("=".repeat(60));
  console.log("  Pair         :", pairAddress);
  console.log("  $GAME reserve:", ethers.formatEther(gameReserve));
  console.log("  ETH reserve  :", ethers.formatEther(ethReserve));
  console.log("  LP tokens    :", ethers.formatEther(lpBalance), "/", ethers.formatEther(lpTotal));
  console.log("  Price        : 1 $GAME =", (parseFloat(ethers.formatEther(ethReserve)) / parseFloat(ethers.formatEther(gameReserve))).toExponential(4), "ETH");
  console.log("=".repeat(60));
}

main().catch((err) => {
  console.error("FAILED:", err.message || err);
  process.exit(1);
});
