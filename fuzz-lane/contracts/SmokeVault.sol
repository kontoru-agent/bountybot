// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @notice Smoke target for the external-compute lane proof.
/// Deliberately sound: the invariant must HOLD, so a green
/// Echidna run proves the pipeline, not a bug.
contract SmokeVault {
    uint256 public totalDeposited;
    mapping(address => uint256) public balanceOf;

    function deposit() external payable {
        balanceOf[msg.sender] += msg.value;
        totalDeposited += msg.value;
    }

    function withdraw(uint256 amount) external {
        require(balanceOf[msg.sender] >= amount, "insufficient");
        balanceOf[msg.sender] -= amount;
        totalDeposited -= amount;
        (bool ok, ) = msg.sender.call{value: amount}("");
        require(ok, "send failed");
    }
}

contract SmokeVaultTest is SmokeVault {
    // Invariant: contract ether balance always equals totalDeposited.
    function echidna_balance_matches_total() public view returns (bool) {
        return address(this).balance == totalDeposited;
    }
}
