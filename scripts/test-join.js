const { ethers } = require("hardhat");

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  const GAME_TOKEN = process.env.GAME_TOKEN_ADDRESS || "0x4d442EC52ce06e7CcD3E88622782736f62DC3843";
  const CLAWGAME   = process.env.CONTRACT_ADDRESS   || "0xf9CCf1Fb4b8600114D2d741e789Ad352d8527E9E";

  const [signer] = await ethers.getSigners();
  console.log("Claw Game - Test Join (Bronze Arena)");
  console.log("Signer:", signer.address);
  console.log("GameToken:", GAME_TOKEN);
  console.log("ClawGame:", CLAWGAME);
  console.log("---");

  const token = await ethers.getContractAt("MockGAME", GAME_TOKEN);
  const claw  = await ethers.getContractAt("ClawGame", CLAWGAME);

  const balance = await token.balanceOf(signer.address);
  console.log("Signer $GAME balance:", ethers.formatEther(balance));

  const t = await claw.tournaments(1);
  const entryFee = t.entryFee;
  console.log("Tournament #1 - Arena:", t.arena.toString(), "State:", t.state.toString());
  console.log("Entry fee:", ethers.formatEther(entryFee), "$GAME");
  console.log("Players:", t.playerCount.toString());

  if (t.state.toString() !== "0") {
    console.log("Tournament is not Open. Aborting.");
    return;
  }

  // Step 1: Approve
  console.log("\n[1/2] Approving ClawGame to spend", ethers.formatEther(entryFee), "$GAME...");
  const approveTx = await token.approve(CLAWGAME, entryFee);
  await approveTx.wait();
  console.log("Approve OK - tx:", approveTx.hash);

  // Wait for nonce to update on testnet
  console.log("Waiting 5s for nonce propagation...");
  await sleep(5000);

  // Step 2: Join tournament
  console.log("\n[2/2] Joining tournament #1 (Bronze)...");
  const joinTx = await claw.join(1, signer.address);
  await joinTx.wait();
  console.log("Join OK - tx:", joinTx.hash);

  // Verify
  const newBalance = await token.balanceOf(signer.address);
  const tAfter = await claw.tournaments(1);
  console.log("\n--- Results ---");
  console.log("New $GAME balance:", ethers.formatEther(newBalance));
  console.log("Players in tournament:", tAfter.playerCount.toString());
  console.log("Test complete!");
}

main().catch((err) => {
  console.error("Error:", err.message || err);
  process.exit(1);
});
