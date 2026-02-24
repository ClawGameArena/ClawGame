const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying to TESTNET (Base Sepolia)");
  console.log("Deployer:", deployer.address);
  console.log("Balance:", hre.ethers.formatEther(await hre.ethers.provider.getBalance(deployer.address)), "ETH");

  // ── 1. Deploy MockGAME token ──
  console.log("\n1. Deploying MockGAME token...");
  const MockGAME = await hre.ethers.getContractFactory("MockGAME");
  const mockGame = await MockGAME.deploy();
  await mockGame.waitForDeployment();
  const tokenAddr = await mockGame.getAddress();
  console.log("   MockGAME deployed:", tokenAddr);

  // ── 2. Deploy ClawGame (2 params: token, treasury) ──
  console.log("\n2. Deploying ClawGame...");
  const ClawGame = await hre.ethers.getContractFactory("ClawGame");
  const clawgame = await ClawGame.deploy(
    tokenAddr,          // gameToken
    deployer.address    // treasury = deployer for testing
  );
  await clawgame.waitForDeployment();
  const contractAddr = await clawgame.getAddress();
  console.log("   ClawGame deployed:", contractAddr);

  // ── 3. Fund ClawGame with test tokens ──
  console.log("\n3. Funding ClawGame with test $GAME...");
  const fundAmount = hre.ethers.parseEther("100000000"); // 100M tokens
  const tx = await mockGame.transfer(contractAddr, fundAmount);
  await tx.wait();
  console.log("   Sent 100M tGAME to contract");

  // ── 4. Create 3 tournaments (Bronze, Silver, Gold) ──
  console.log("\n4. Creating initial tournaments...");
  
  // Entry fees in $GAME (18 decimals)
  // Bronze ~$5, Silver ~$50, Gold ~$500
  const fees = [
    hre.ethers.parseEther("5000"),     // Bronze: 5,000 $GAME
    hre.ethers.parseEther("50000"),    // Silver: 50,000 $GAME
    hre.ethers.parseEther("500000"),   // Gold: 500,000 $GAME
  ];
  const arenaNames = ["Bronze", "Silver", "Gold"];

  for (let i = 0; i < 3; i++) {
    const createTx = await clawgame.createTournament(i, fees[i]);
    await createTx.wait();
    console.log(`   ${arenaNames[i]} tournament #${i} created (fee: ${hre.ethers.formatEther(fees[i])} $GAME)`);
  }

  // ── 5. Verify setup ──
  console.log("\n5. Verifying...");
  const stats = await clawgame.getStats();
  console.log(`   Tournaments created: ${stats[3].toString()}`);
  
  for (let i = 0; i < 3; i++) {
    const t = await clawgame.getTournament(i);
    console.log(`   Tournament #${i}: arena=${arenaNames[t[0]]}, state=${t[1] == 0 ? 'OPEN' : t[1]}, fee=${hre.ethers.formatEther(t[2])} $GAME`);
  }

  // ── Summary ──
  console.log("\n════════════════════════════════════════");
  console.log("  TESTNET DEPLOYMENT COMPLETE");
  console.log("════════════════════════════════════════");
  console.log("MockGAME Token:", tokenAddr);
  console.log("ClawGame Contract:", contractAddr);
  console.log("Treasury:", deployer.address);
  console.log("\nUpdate your .env:");
  console.log(`  GAME_TOKEN_ADDRESS=${tokenAddr}`);
  console.log(`  CONTRACT_ADDRESS=${contractAddr}`);
  console.log("\nGet testnet ETH: https://www.alchemy.com/faucets/base-sepolia");
  console.log("Note: joinWithETH won't work on testnet (no DEX).");
  console.log("Use join() with test tokens (mint via MockGAME.mint())");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
