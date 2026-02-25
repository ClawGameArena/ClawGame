// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * SwapHelper — wraps Uniswap V2 Router for ClawGame.joinWithETH()
 * Receives ETH, swaps for $GAME via Uniswap, sends tokens to `to`.
 */

interface IUniswapV2Router {
    function swapExactETHForTokens(
        uint amountOutMin,
        address[] calldata path,
        address to,
        uint deadline
    ) external payable returns (uint[] memory amounts);

    function getAmountsOut(uint amountIn, address[] calldata path)
        external view returns (uint[] memory amounts);

    function WETH() external view returns (address);
}

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

contract SwapHelper {
    IUniswapV2Router public immutable router;
    address public immutable weth;

    constructor(address _router) {
        router = IUniswapV2Router(_router);
        weth = router.WETH();
    }

    /**
     * @notice Swap ETH for token via Uniswap V2
     * @param token The token to buy
     * @param minOut Minimum tokens to receive
     * @param to Recipient of the tokens
     * @return amount Tokens received
     */
    function swapETHForToken(
        address token,
        uint256 minOut,
        address to
    ) external payable returns (uint256 amount) {
        address[] memory path = new address[](2);
        path[0] = weth;
        path[1] = token;

        uint[] memory amounts = router.swapExactETHForTokens{value: msg.value}(
            minOut,
            path,
            to,
            block.timestamp + 300
        );

        amount = amounts[amounts.length - 1];
    }

    /// @notice Preview: how many tokens for given ETH
    function getAmountOut(address token, uint256 ethAmount) external view returns (uint256) {
        address[] memory path = new address[](2);
        path[0] = weth;
        path[1] = token;
        uint[] memory amounts = router.getAmountsOut(ethAmount, path);
        return amounts[amounts.length - 1];
    }

    /// @notice Preview: how much ETH needed for given token amount
    function getAmountIn(address token, uint256 tokenAmount) external view returns (uint256) {
        // Use getAmountsOut in reverse by binary search is complex,
        // so we provide a simple estimate: iterate from getAmountsOut
        // For UI, just overshoot with slippage
        revert("Use router.getAmountsIn directly");
    }

    receive() external payable {}
}
