const { ethers } = require("hardhat");

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  const [deployer] = await ethers.getSigners();
  const ROUTER = "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24"; // Uniswap V2 Router on Base
  const CLAWGAME = "0xfa6D6407e8CD8b2b63eFAAc7d258D584c00BDe0E";

  console.log("Deployer:", deployer.address);
  console.log("ETH:", ethers.formatEther(await ethers.provider.getBalance(deployer.address)));

  // Deploy SwapHelper
  console.log("\n[1/2] Deploying SwapHelper...");
  const SwapHelper = await ethers.getContractFactory("SwapHelper");
  const sh = await SwapHelper.deploy(ROUTER);
  await sh.waitForDeployment();
  const shAddr = await sh.getAddress();
  console.log("SwapHelper:", shAddr);

  await sleep(5000);

  // Set SwapHelper on ClawGame
  console.log("\n[2/2] Setting SwapHelper on ClawGame...");
  const claw = await ethers.getContractAt("ClawGame", CLAWGAME);
  const tx = await claw.setSwapHelper(shAddr);
  await tx.wait();
  console.log("setSwapHelper OK - tx:", tx.hash);

  // Verify
  const currentSH = await claw.swapHelper();
  console.log("ClawGame.swapHelper:", currentSH);
  console.log("\nDone! joinWithETH() is now enabled.");
  console.log("VERIFY: npx hardhat verify --network base " + shAddr + " " + ROUTER);
}

main().catch(err => { console.error("FAILED:", err.message); process.exit(1); });
