async function main() {
  const token = await ethers.getContractAt("MockGAME", "0x4d442EC52ce06e7CcD3E88622782736f62DC3843");
  const [signer] = await ethers.getSigners();
  const balance = await token.balanceOf(signer.address);
  console.log("Signer:", signer.address);
  console.log("Current $GAME balance:", ethers.formatEther(balance));

  console.log("Transferring 100M $GAME to ClawGame contract...");
  const nonce = await signer.getNonce();
  console.log("Using nonce:", nonce);
  const transferTx = await token.transfer("0xf9CCf1Fb4b8600114D2d741e789Ad352d8527E9E", ethers.parseEther("100000000"), { nonce: nonce });
  await transferTx.wait();
  console.log("Transfer OK - tx:", transferTx.hash);

  const contractBalance = await token.balanceOf("0xf9CCf1Fb4b8600114D2d741e789Ad352d8527E9E");
  console.log("ClawGame contract balance:", ethers.formatEther(contractBalance), "$GAME");
}
main().catch(console.error);
