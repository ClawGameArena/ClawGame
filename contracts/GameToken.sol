// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * ╔═══════════════════════════════════════════════════════════╗
 * ║                    $GAME TOKEN                           ║
 * ║             Claw Game Arena — ERC-20                      ║
 * ║         Fixed supply · No mint · No owner                 ║
 * ╚═══════════════════════════════════════════════════════════╝
 *
 * Total supply: 1,000,000,000 GAME (1 billion)
 * All tokens minted to deployer at construction.
 * No mint, no burn by owner, no admin functions.
 */

contract GameToken {
    string public constant name     = "Claw Game";
    string public constant symbol   = "GAME";
    uint8  public constant decimals = 18;
    uint256 public constant totalSupply = 1_000_000_000 * 1e18; // 1 billion

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    constructor() {
        balanceOf[msg.sender] = totalSupply;
        emit Transfer(address(0), msg.sender, totalSupply);
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "Insufficient balance");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        emit Transfer(msg.sender, to, amount);
        return true;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(balanceOf[from] >= amount, "Insufficient balance");
        require(allowance[from][msg.sender] >= amount, "Not approved");
        balanceOf[from] -= amount;
        allowance[from][msg.sender] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
        return true;
    }
}
