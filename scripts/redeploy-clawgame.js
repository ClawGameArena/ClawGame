const { ethers } = require("hardhat");

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  const [deployer] = await ethers.getSigners();
  const TOKEN   = "0x4d442EC52ce06e7CcD3E88622782736f62DC3843";
  const TREASURY = "0x1F3437Cd88eBEc6576707C5962Cc3dC29a8076d2";

  console.log("=".repeat(60));
  console.log("  REDEPLOY ClawGame (maxPlayers=25)");
  console.log("=".repeat(60));
  console.log("Deployer:", deployer.address);
  console.log("Token   :", TOKEN);
  console.log("Treasury:", TREASURY);

  const ethBal = await ethers.provider.getBalance(deployer.address);
  console.log("ETH bal :", ethers.formatEther(ethBal));
  console.log("=".repeat(60));

  // ── Deploy new ClawGame ──
  console.log("\n[1/2] Deploying new ClawGame...");
  const ClawGame = await ethers.getContractFactory("ClawGame");
  const claw = await ClawGame.deploy(TOKEN, TREASURY);
  console.log("  Deploy tx sent, waiting...");
  await claw.waitForDeployment();
  const addr = await claw.getAddress();
  console.log("  ClawGame deployed at:", addr);

  await sleep(10000);

  // Verify
  const mp = await claw.maxPlayers();
  console.log("  maxPlayers:", mp.toString());
  console.log("  owner:", await claw.owner());

  // ── Create 3 tournaments ──
  // Entry fees: Bronze=1000, Silver=10000, Gold=100000 $GAME
  const BRONZE_FEE = ethers.parseEther("1000");
  const SILVER_FEE = ethers.parseEther("10000");
  const GOLD_FEE   = ethers.parseEther("100000");

  console.log("\n[2/2] Creating tournaments...");

  console.log("  Creating Bronze (arena=0, 1000 $GAME)...");
  const tx1 = await claw.createTournament(0, BRONZE_FEE);
  await tx1.wait();
  console.log("  Bronze OK - tx:", tx1.hash);

  await sleep(5000);

  console.log("  Creating Silver (arena=1, 10000 $GAME)...");
  const tx2 = await claw.createTournament(1, SILVER_FEE);
  await tx2.wait();
  console.log("  Silver OK - tx:", tx2.hash);

  await sleep(5000);

  console.log("  Creating Gold (arena=2, 100000 $GAME)...");
  const tx3 = await claw.createTournament(2, GOLD_FEE);
  await tx3.wait();
  console.log("  Gold OK - tx:", tx3.hash);

  await sleep(5000);

  // Verify tournaments
  for (let i = 0; i < 3; i++) {
    const t = await claw.tournaments(i);
    console.log(`  Tournament #${i}: arena=${t.arena} fee=${ethers.formatEther(t.entryFee)} state=${t.state} players=${t.playerCount}`);
  }

  // ── Summary ──
  console.log("\n" + "=".repeat(60));
  console.log("  REDEPLOY COMPLETE");
  console.log("=".repeat(60));
  console.log("  NEW ClawGame :", addr);
  console.log("  maxPlayers   : 25");
  console.log("  Tournaments  : 3 (Bronze, Silver, Gold)");
  console.log("  Token        :", TOKEN);
  console.log("  Treasury     :", TREASURY);
  console.log("=".repeat(60));
  console.log("\n  UPDATE .env: CONTRACT_ADDRESS=" + addr);
  console.log("  VERIFY: npx hardhat verify --network base " + addr + " " + TOKEN + " " + TREASURY);
  console.log("=".repeat(60));
}

main().catch((err) => {
  console.error("FAILED:", err.message || err);
  process.exit(1);
});
