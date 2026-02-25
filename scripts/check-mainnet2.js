const { ethers } = require("hardhat");
async function main() {
  const [s] = await ethers.getSigners();
  const token = await ethers.getContractAt("GameToken", "0x4d442EC52ce06e7CcD3E88622782736f62DC3843");

  const name = await token.name();
  const symbol = await token.symbol();
  const supply = await token.totalSupply();
  const bal = await token.balanceOf(s.address);
  const balTreasury = await token.balanceOf("0x1F3437Cd88eBEc6576707C5962Cc3dC29a8076d2");
  const balTeam = await token.balanceOf("0x80233Ef1C9c9C690dd9ac78B16629E230C12a010");

  console.log("Token:", name, "(" + symbol + ")");
  console.log("Total supply:", ethers.formatEther(supply));
  console.log("Deployer bal:", ethers.formatEther(bal));
  console.log("Treasury bal:", ethers.formatEther(balTreasury));
  console.log("Team bal    :", ethers.formatEther(balTeam));
  console.log("Nonce       :", await s.getNonce());
}
main().catch(console.error);
