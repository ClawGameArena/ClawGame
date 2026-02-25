const { ethers } = require("hardhat");
async function main() {
  const claw = await ethers.getContractAt("ClawGame", "0xfa6D6407e8CD8b2b63eFAAc7d258D584c00BDe0E");
  const count = await claw.nextTournamentId();
  const mp = await claw.maxPlayers();
  console.log("nextTournamentId:", count.toString());
  console.log("maxPlayers:", mp.toString());
  for (let i = 0; i < Number(count); i++) {
    const t = await claw.tournaments(i);
    console.log(`Tournament #${i}: arena=${t.arena} fee=${ethers.formatEther(t.entryFee)} state=${t.state} players=${t.playerCount}`);
  }
}
main().catch(console.error);
