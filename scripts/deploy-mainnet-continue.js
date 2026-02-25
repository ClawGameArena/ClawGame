const { ethers } = require("hardhat");

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  const [deployer] = await ethers.getSigners();
  const TOKEN_ADDRESS = "0x4d442EC52ce06e7CcD3E88622782736f62DC3843";
  const TREASURY = "0x1F3437Cd88eBEc6576707C5962Cc3dC29a8076d2";
  const TEAM     = "0x80233Ef1C9c9C690dd9ac78B16629E230C12a010";

  console.log("=".repeat(60));
  console.log("  CLAW GAME — MAINNET DEPLOYMENT (CONTINUE)");
  console.log("=".repeat(60));
  console.log("Deployer  :", deployer.address);
  console.log("GameToken :", TOKEN_ADDRESS);
  console.log("Treasury  :", TREASURY);
  console.log("Team      :", TEAM);

  const token = await ethers.getContractAt("GameToken", TOKEN_ADDRESS);
  const bal = await token.balanceOf(deployer.address);
  console.log("Deployer $GAME:", ethers.formatEther(bal));
  console.log("=".repeat(60));

  // ════════════════════════════════════════════
  //  STEP 1 — Distribute tokens
  // ════════════════════════════════════════════
  const TREASURY_AMOUNT = ethers.parseEther("350000000"); // 350M
  const TEAM_AMOUNT     = ethers.parseEther("250000000"); // 250M

  console.log("\n[1/2] Distributing tokens...");

  // Transfer to Treasury
  console.log("  Sending 350M $GAME to Treasury...");
  const tx1 = await token.transfer(TREASURY, TREASURY_AMOUNT);
  console.log("  tx1 hash:", tx1.hash);
  console.log("  Waiting for confirmation...");
  await tx1.wait();
  console.log("  350M to Treasury OK");

  console.log("  Waiting 10s before next tx...");
  await sleep(10000);

  // Transfer to Team
  console.log("  Sending 250M $GAME to Team...");
  const tx2 = await token.transfer(TEAM, TEAM_AMOUNT);
  console.log("  tx2 hash:", tx2.hash);
  console.log("  Waiting for confirmation...");
  await tx2.wait();
  console.log("  250M to Team OK");

  await sleep(10000);

  // Verify
  const balDeployer = await token.balanceOf(deployer.address);
  const balTreasury = await token.balanceOf(TREASURY);
  const balTeam     = await token.balanceOf(TEAM);
  console.log("\n  Distribution verified:");
  console.log("  Deployer (LP) :", ethers.formatEther(balDeployer), "$GAME");
  console.log("  Treasury      :", ethers.formatEther(balTreasury), "$GAME");
  console.log("  Team          :", ethers.formatEther(balTeam), "$GAME");

  // ════════════════════════════════════════════
  //  STEP 2 — Deploy ClawGame
  // ════════════════════════════════════════════
  console.log("\n[2/2] Deploying ClawGame contract...");
  console.log("  Waiting 10s before deploy...");
  await sleep(10000);

  const ClawGame = await ethers.getContractFactory("ClawGame");
  const claw = await ClawGame.deploy(TOKEN_ADDRESS, TREASURY);
  console.log("  Deploy tx sent, waiting for confirmation...");
  await claw.waitForDeployment();
  const clawAddress = await claw.getAddress();

  await sleep(5000);

  const clawOwner = await claw.owner();
  const clawToken = await claw.gameToken();
  console.log("  ClawGame deployed at:", clawAddress);
  console.log("  Owner  :", clawOwner);
  console.log("  Token  :", clawToken);

  // ════════════════════════════════════════════
  //  SUMMARY
  // ════════════════════════════════════════════
  console.log("\n" + "=".repeat(60));
  console.log("  DEPLOYMENT COMPLETE");
  console.log("=".repeat(60));
  console.log("  GameToken  :", TOKEN_ADDRESS);
  console.log("  ClawGame   :", clawAddress);
  console.log("  Treasury   :", TREASURY);
  console.log("  Team       :", TEAM);
  console.log("  Deployer   :", deployer.address);
  console.log("=".repeat(60));
  console.log("\n  UPDATE .env:");
  console.log("  GAME_TOKEN_ADDRESS=" + TOKEN_ADDRESS);
  console.log("  CONTRACT_ADDRESS=" + clawAddress);
  console.log("=".repeat(60));
}

main().catch((err) => {
  console.error("FAILED:", err.message || err);
  process.exit(1);
});
