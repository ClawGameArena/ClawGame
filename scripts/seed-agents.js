const { ethers } = require("hardhat");
const fs = require("fs");

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

const ROUTER_ABI = [
  "function swapExactETHForTokens(uint amountOutMin, address[] calldata path, address to, uint deadline) external payable returns (uint[] memory amounts)"
];
const ERC20_ABI = [
  "function approve(address spender, uint256 amount) external returns (bool)",
  "function balanceOf(address account) external view returns (uint256)"
];
const CLAW_ABI = [
  "function join(uint256 tid, address creator) external",
  "function tournaments(uint256) external view returns (uint8 arena, uint8 state, uint96 entryFee, uint256 prizePool, uint32 playerCount, uint40 createdAt)"
];

async function main() {
  const [deployer] = await ethers.getSigners();
  const GAME_TOKEN = "0x4d442EC52ce06e7CcD3E88622782736f62DC3843";
  const CLAWGAME   = "0xfa6D6407e8CD8b2b63eFAAc7d258D584c00BDe0E";
  const ROUTER     = "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24";
  const WETH       = "0x4200000000000000000000000000000000000006";

  console.log("=".repeat(60));
  console.log("  SEED 5 AGENTS v2");
  console.log("=".repeat(60));

  const claw = new ethers.Contract(CLAWGAME, CLAW_ABI, deployer);
  const t = await claw.tournaments(0);
  const entryFee = t.entryFee;
  console.log("Bronze entry fee:", ethers.formatEther(entryFee), "$GAME");
  console.log("Deployer ETH:", ethers.formatEther(await ethers.provider.getBalance(deployer.address)));

  // Generate 5 wallets and save FIRST
  const agents = [];
  for (let i = 0; i < 5; i++) {
    const w = ethers.Wallet.createRandom().connect(ethers.provider);
    agents.push({ name: `Agent-${String(i+1).padStart(3,"0")}`, wallet: w, address: w.address, privateKey: w.privateKey });
  }
  // Save immediately
  fs.writeFileSync("/root/clawgame/seed-agents.json", JSON.stringify(agents.map(a => ({ name: a.name, address: a.address, privateKey: a.privateKey })), null, 2));
  console.log("Wallets saved to seed-agents.json");
  agents.forEach(a => console.log(`  ${a.name}: ${a.address}`));

  // Fund: 0.002 ETH per agent (swap + approve + join gas)
  const FUND = ethers.parseEther("0.002");
  console.log("\n[1/4] Funding agents...");
  for (let i = 0; i < 5; i++) {
    const tx = await deployer.sendTransaction({ to: agents[i].address, value: FUND });
    await tx.wait();
    console.log(`  ${agents[i].name} funded - tx: ${tx.hash}`);
    await sleep(3000);
  }
  await sleep(5000);

  // Register via API
  console.log("\n[2/4] Registering via API...");
  for (const a of agents) {
    try {
      const resp = await fetch("http://localhost:8000/api/v1/agents/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: a.name, wallet_address: a.address, creator_address: a.address }),
      });
      console.log(`  ${a.name}: ${resp.status}`);
    } catch (e) {
      console.log(`  ${a.name} API err: ${e.message}`);
    }
  }

  // Swap ETH -> GAME (0.00005 ETH each, should get ~2700 GAME at current price)
  const SWAP_ETH = ethers.parseEther("0.00005");
  const path = [WETH, GAME_TOKEN];
  const deadline = Math.floor(Date.now() / 1000) + 1800;

  console.log("\n[3/4] Swapping ETH -> $GAME...");
  for (let i = 0; i < 5; i++) {
    try {
      const agentRouter = new ethers.Contract(ROUTER, ROUTER_ABI, agents[i].wallet);
      const swapTx = await agentRouter.swapExactETHForTokens(0, path, agents[i].address, deadline, { value: SWAP_ETH });
      await swapTx.wait();
      await sleep(3000);
      const bal = await new ethers.Contract(GAME_TOKEN, ERC20_ABI, ethers.provider).balanceOf(agents[i].address);
      console.log(`  ${agents[i].name}: ${ethers.formatEther(bal)} $GAME - tx: ${swapTx.hash}`);
    } catch (e) {
      console.log(`  ${agents[i].name} SWAP FAILED: ${e.message.slice(0, 80)}`);
    }
    await sleep(5000);
  }

  // Approve + Join
  console.log("\n[4/4] Approve + Join Bronze...");
  for (let i = 0; i < 5; i++) {
    try {
      const token = new ethers.Contract(GAME_TOKEN, ERC20_ABI, agents[i].wallet);
      const agentClaw = new ethers.Contract(CLAWGAME, CLAW_ABI, agents[i].wallet);

      const appTx = await token.approve(CLAWGAME, entryFee);
      await appTx.wait();
      await sleep(5000);

      const joinTx = await agentClaw.join(0, agents[i].address);
      await joinTx.wait();
      console.log(`  ${agents[i].name} JOINED - tx: ${joinTx.hash}`);
    } catch (e) {
      console.log(`  ${agents[i].name} JOIN FAILED: ${e.message.slice(0, 100)}`);
    }
    await sleep(5000);
  }

  // Final state
  await sleep(5000);
  const tAfter = await claw.tournaments(0);
  console.log("\n" + "=".repeat(60));
  console.log("  SEED COMPLETE");
  console.log("  Bronze players:", tAfter.playerCount.toString(), "/ 25");
  console.log("=".repeat(60));
}

main().catch((err) => {
  console.error("FAILED:", err.message || err);
  process.exit(1);
});
