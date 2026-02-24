require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

// Handle PRIVATE_KEY with or without 0x prefix
function getAccounts() {
  let key = process.env.PRIVATE_KEY || "";
  if (!key) return [];
  if (!key.startsWith("0x")) key = "0x" + key;
  return [key];
}

module.exports = {
  solidity: {
    version: "0.8.24",
    settings: { optimizer: { enabled: true, runs: 200 } },
  },
  networks: {
    baseSepolia: {
      url: process.env.BASE_RPC_URL || "https://sepolia.base.org",
      chainId: 84532,
      accounts: getAccounts(),
    },
    base: {
      url: process.env.BASE_RPC_URL || "https://mainnet.base.org",
      chainId: 8453,
      accounts: getAccounts(),
    },
  },
  etherscan: {
    apiKey: {
      base: process.env.BASESCAN_API_KEY || "",
      baseSepolia: process.env.BASESCAN_API_KEY || "",
    },
    customChains: [
      { network: "base", chainId: 8453, urls: { apiURL: "https://api.basescan.org/api", browserURL: "https://basescan.org" } },
      { network: "baseSepolia", chainId: 84532, urls: { apiURL: "https://api-sepolia.basescan.org/api", browserURL: "https://sepolia.basescan.org" } },
    ],
  },
};
