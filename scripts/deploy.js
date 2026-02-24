const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying to MAINNET (Base)");
  console.log("Deployer:", deployer.address);

  const GAME_TOKEN = process.env.GAME_TOKEN_ADDRESS;
  const TREASURY = process.env.TREASURY_WALLET || deployer.address;

  if (!GAME_TOKEN || GAME_TOKEN === "0x...") {
    console.error("ERROR: Set GAME_TOKEN_ADDRESS in .env first!");
    console.error("Deploy your token via flaunch.gg, then set the address.");
    process.exit(1);
  }

  console.log("Token:", GAME_TOKEN);
  console.log("Treasury:", TREASURY);

  // ── Deploy ClawGame (2 params: token, treasury) ──
  const ClawGame = await hre.ethers.getContractFactory("ClawGame");
  const clawgame = await ClawGame.deploy(GAME_TOKEN, TREASURY);
  await clawgame.waitForDeployment();
  const addr = await clawgame.getAddress();
  console.log("ClawGame deployed:", addr);

  // ── Create initial tournaments ──
  console.log("\nCreating tournaments...");
  const fees = [
    hre.ethers.parseEther("5000"),
    hre.ethers.parseEther("50000"),
    hre.ethers.parseEther("500000"),
  ];
  for (let i = 0; i < 3; i++) {
    const tx = await clawgame.createTournament(i, fees[i]);
    await tx.wait();
    console.log(`  Arena ${i} created`);
  }

  // ── Verify contract on BaseScan ──
  console.log("\nVerifying on BaseScan...");
  try {
    await hre.run("verify:verify", {
      address: addr,
      constructorArguments: [GAME_TOKEN, TREASURY],
    });
    console.log("Verified ✓");
  } catch (e) {
    console.log("Verify later:", e.message);
  }

  console.log("\n════════════════════════════════════════");
  console.log("  MAINNET DEPLOYMENT COMPLETE");
  console.log("════════════════════════════════════════");
  console.log("ClawGame:", addr);
  console.log("Update .env: CONTRACT_ADDRESS=" + addr);
  console.log("\nDon't forget to setSwapHelper() once you have a DEX router.");
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
