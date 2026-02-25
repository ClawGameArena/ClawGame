const { ethers } = require("hardhat");
async function main() {
  const claw = await ethers.getContractAt("ClawGame", "0x0496a1e78e804aB27da9AF8003C071A729078464");
  const count = await claw.nextTournamentId();
  console.log("Total tournaments:", count.toString());
  for (let i = 0; i < Number(count); i++) {
    const t = await claw.tournaments(i);
    console.log(`Tournament #${i}: arena=${t.arena} entryFee=${t.entryFee.toString()} (${ethers.formatEther(t.entryFee)} $GAME) state=${t.state} players=${t.playerCount}`);
  }
}
main().catch(console.error);
