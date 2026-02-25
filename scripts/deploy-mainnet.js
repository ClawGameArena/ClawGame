const { ethers } = require("hardhat");

/**
 * ╔═══════════════════════════════════════════════════════════╗
 * ║          CLAW GAME — MAINNET DEPLOYMENT                  ║
 * ║                                                           ║
 * ║  1. Deploy GameToken (1B fixed supply)                    ║
 * ║  2. Distribute tokens per whitepaper                      ║
 * ║  3. Deploy ClawGame contract                              ║
 * ╚═══════════════════════════════════════════════════════════╝
 */

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  const [deployer] = await ethers.getSigners();

  // ── Wallets ──
  const TREASURY = "0x1F3437Cd88eBEc6576707C5962Cc3dC29a8076d2"; // Treasury (20%) + Community (15%)
  const TEAM     = "0x80233Ef1C9c9C690dd9ac78B16629E230C12a010"; // Team (15%) + Reserve (10%)

  console.log("=".repeat(60));
  console.log("  CLAW GAME — MAINNET DEPLOYMENT");
  console.log("=".repeat(60));
  console.log("Deployer :", deployer.address);
  console.log("Treasury :", TREASURY);
  console.log("Team     :", TEAM);
  console.log("Network  : Base Mainnet (chainId 8453)");

  const ethBalance = await ethers.provider.getBalance(deployer.address);
  console.log("ETH bal  :", ethers.formatEther(ethBalance), "ETH");
  console.log("=".repeat(60));

  if (ethBalance === 0n) {
    console.log("ERROR: No ETH for gas. Fund deployer wallet first.");
    process.exit(1);
  }

  // ════════════════════════════════════════════
  //  STEP 1 — Deploy GameToken ($GAME)
  // ════════════════════════════════════════════
  console.log("\n[1/3] Deploying GameToken (ERC-20, 1B fixed supply)...");
  const GameToken = await ethers.getContractFactory("GameToken");
  const token = await GameToken.deploy();
  await token.waitForDeployment();
  const tokenAddress = await token.getAddress();
  console.log("  GameToken deployed at:", tokenAddress);

  const totalSupply = await token.totalSupply();
  const deployerBal = await token.balanceOf(deployer.address);
  console.log("  Total supply:", ethers.formatEther(totalSupply), "$GAME");
  console.log("  Deployer bal:", ethers.formatEther(deployerBal), "$GAME");

  console.log("  Waiting 5s for block confirmation...");
  await sleep(5000);

  // ════════════════════════════════════════════
  //  STEP 2 — Distribute tokens per whitepaper
  // ════════════════════════════════════════════
  //  400M (40%) → Deployer   (reserved for Uniswap LP)
  //  350M (35%) → Treasury   (20% treasury + 15% community)
  //  250M (25%) → Team       (15% team + 10% reserve)

  const TREASURY_AMOUNT = ethers.parseEther("350000000"); // 350M
  const TEAM_AMOUNT     = ethers.parseEther("250000000"); // 250M

  console.log("\n[2/3] Distributing tokens per whitepaper...");

  // Transfer to Treasury
  console.log("  Sending 350M $GAME to Treasury (20% treasury + 15% community)...");
  const tx1 = await token.transfer(TREASURY, TREASURY_AMOUNT);
  await tx1.wait();
  console.log("  Transfer OK - tx:", tx1.hash);

  console.log("  Waiting 5s...");
  await sleep(5000);

  // Transfer to Team
  console.log("  Sending 250M $GAME to Team (15% team + 10% reserve)...");
  const tx2 = await token.transfer(TEAM, TEAM_AMOUNT);
  await tx2.wait();
  console.log("  Transfer OK - tx:", tx2.hash);

  await sleep(5000);

  // Verify balances
  const balDeployer = await token.balanceOf(deployer.address);
  const balTreasury = await token.balanceOf(TREASURY);
  const balTeam     = await token.balanceOf(TEAM);

  console.log("\n  Distribution summary:");
  console.log("  ┌─────────────────────────────────────────────────────┐");
  console.log("  │ Deployer (LP pool)   : 400,000,000 $GAME    (40%) │");
  console.log("  │ Treasury wallet      : 350,000,000 $GAME    (35%) │");
  console.log("  │   ├─ Treasury        : 200,000,000          (20%) │");
  console.log("  │   └─ Community       : 150,000,000          (15%) │");
  console.log("  │ Team wallet          : 250,000,000 $GAME    (25%) │");
  console.log("  │   ├─ Team (vesting)  : 150,000,000          (15%) │");
  console.log("  │   └─ Reserve         : 100,000,000          (10%) │");
  console.log("  └─────────────────────────────────────────────────────┘");
  console.log("  Deployer actual:", ethers.formatEther(balDeployer), "$GAME");
  console.log("  Treasury actual:", ethers.formatEther(balTreasury), "$GAME");
  console.log("  Team actual    :", ethers.formatEther(balTeam), "$GAME");

  // ════════════════════════════════════════════
  //  STEP 3 — Deploy ClawGame contract
  // ════════════════════════════════════════════
  console.log("\n[3/3] Deploying ClawGame contract...");
  const ClawGame = await ethers.getContractFactory("ClawGame");
  const claw = await ClawGame.deploy(tokenAddress, TREASURY);
  await claw.waitForDeployment();
  const clawAddress = await claw.getAddress();
  console.log("  ClawGame deployed at:", clawAddress);

  const clawOwner = await claw.owner();
  const clawToken = await claw.gameToken();
  console.log("  Owner  :", clawOwner);
  console.log("  Token  :", clawToken);

  // ════════════════════════════════════════════
  //  SUMMARY
  // ════════════════════════════════════════════
  console.log("\n" + "=".repeat(60));
  console.log("  DEPLOYMENT COMPLETE");
  console.log("=".repeat(60));
  console.log("  GameToken  :", tokenAddress);
  console.log("  ClawGame   :", clawAddress);
  console.log("  Treasury   :", TREASURY);
  console.log("  Team       :", TEAM);
  console.log("  Deployer   :", deployer.address);
  console.log("=".repeat(60));
  console.log("\n  NEXT STEPS:");
  console.log("  1. Update .env:");
  console.log("     GAME_TOKEN_ADDRESS=" + tokenAddress);
  console.log("     CONTRACT_ADDRESS=" + clawAddress);
  console.log("  2. Verify contracts on BaseScan");
  console.log("  3. Add LP on Uniswap (400M $GAME from deployer)");
  console.log("  4. Create tournaments via API");
  console.log("  5. systemctl restart clawgame-api");
  console.log("=".repeat(60));
}

main().catch((err) => {
  console.error("DEPLOYMENT FAILED:", err.message || err);
  process.exit(1);
});
