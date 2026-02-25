const { ethers } = require("hardhat");
const PAIR_ABI = [
  "function getReserves() external view returns (uint112 reserve0, uint112 reserve1, uint32)",
  "function token0() external view returns (address)"
];
const CLAW_ABI = [
  "function tournaments(uint256) external view returns (uint8,uint8,uint96,uint256,uint32,uint40)"
];
async function main() {
  const pair = new ethers.Contract("0x4B7219CA42041516AbF4D27ACcF38a80113e7C82", PAIR_ABI, ethers.provider);
  const [r0, r1] = await pair.getReserves();
  const t0 = await pair.token0();
  const isGameT0 = t0.toLowerCase() === "0x4d442ec52ce06e7ccd3e88622782736f62dc3843";
  const gameR = isGameT0 ? r0 : r1;
  const ethR = isGameT0 ? r1 : r0;
  console.log("Pool reserves:");
  console.log("  $GAME:", ethers.formatEther(gameR));
  console.log("  ETH  :", ethers.formatEther(ethR));
  console.log("  Price: 1 $GAME =", (parseFloat(ethers.formatEther(ethR)) / parseFloat(ethers.formatEther(gameR))).toExponential(4), "ETH");

  // Check tournament state
  const claw = new ethers.Contract("0xfa6D6407e8CD8b2b63eFAAc7d258D584c00BDe0E", CLAW_ABI, ethers.provider);
  const t = await claw.tournaments(0);
  console.log("\nBronze tournament: players=" + t[4].toString() + " state=" + t[1].toString());

  // Check deployer ETH
  const [d] = await ethers.getSigners();
  console.log("Deployer ETH:", ethers.formatEther(await ethers.provider.getBalance(d.address)));
}
main().catch(console.error);
