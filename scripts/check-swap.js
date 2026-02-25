const { ethers } = require("hardhat");
async function main() {
  const claw = await ethers.getContractAt("ClawGame", "0xfa6D6407e8CD8b2b63eFAAc7d258D584c00BDe0E");
  const sh = await claw.swapHelper();
  console.log("swapHelper:", sh);
  console.log("Is zero:", sh === "0x0000000000000000000000000000000000000000");
}
main().catch(console.error);
