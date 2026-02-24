async function main() {
  const token = await ethers.getContractAt("MockGAME", "0x4d442EC52ce06e7CcD3E88622782736f62DC3843");
  const [signer] = await ethers.getSigners();
  
  const signerBal = await token.balanceOf(signer.address);
  console.log("Signer balance:", ethers.formatEther(signerBal), "$GAME");
  
  const contractBal = await token.balanceOf("0xf9CCf1Fb4b8600114D2d741e789Ad352d8527E9E");
  console.log("ClawGame balance:", ethers.formatEther(contractBal), "$GAME");
  
  const totalSupply = await token.totalSupply();
  console.log("Total supply:", ethers.formatEther(totalSupply), "$GAME");
}
main().catch(console.error);
