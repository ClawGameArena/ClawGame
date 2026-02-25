const { ethers } = require("hardhat");
async function main() {
  const [s] = await ethers.getSigners();
  const n = await s.getNonce();
  const b = await ethers.provider.getBalance(s.address);
  console.log("Address:", s.address);
  console.log("Nonce:", n);
  console.log("ETH:", ethers.formatEther(b));
  const code = await ethers.provider.getCode("0x4d442EC52ce06e7CcD3E88622782736f62DC3843");
  console.log("Code at 0x4d44...:", code.length > 2 ? "CONTRACT EXISTS (" + code.length + " bytes)" : "EMPTY");
}
main().catch(console.error);
