pragma solidity ^0.4.11;
 
contract Auction {
    // ---- constants --------------------------------------------------------

    // length of commit in bits
    uint constant private COMMIT_LENGTH = 80;
    
    // length of commit window in blocks
    uint constant public COMMIT_WINDOW = 100;
    
    // length of reveal window in blocks
    uint constant public REVEAL_WINDOW = 100;
    
    // minimum amount of gas required for finalization
    // guarantees that we will always make progress
    uint256 constant public FINALIZE_MIN_GAS = 1600000;

    // ---- fields -----------------------------------------------------------

    address private rootForwarder;

    // Minimum amount of gas required for cloning a forwarder with some
    // slack added on top to make sure that there are no out-of-gas errors
    uint public cloneMinGas;

    // Highest bidder and highest bid. Gets updated whenever there is a 
    // new highest bidder.
    address public highestBidder;
    uint public highestBid;

    // Auction winner. Stays 0 until end of auction.
    address public winner;

    // First block of auction
    uint public startBlock;

    // ---- constructor ------------------------------------------------------

    function Auction() {
        rootForwarder = createRootForwarder();

        uint gas0 = msg.gas;
        assert(rootForwarder.call());
        uint gas1 = msg.gas;
        cloneMinGas = gas0 - gas1 + 30000;

        startBlock = block.number;
    }
    
    // ---- internal methods -------------------------------------------------

    function createRootForwarder() internal returns (address) {
        address self = this;
        address root_forwarder;
        assembly {
            //                                                             5860
            // 0c8038038082843982f358730000000000000000000000000000000000000000
            // 8033143602603b576b58600c8038038082843982f38252388083602039600c01
            // 601483f0005b8180808030318587f1
            //                              10000000000000000000000000000000000
            let solidity_free_mem_ptr := mload(0x40)
            mstore(add(0, solidity_free_mem_ptr), 0x5860)
            mstore(add(32, solidity_free_mem_ptr), or(0x0c8038038082843982f358730000000000000000000000000000000000000000, self))
            mstore(add(64, solidity_free_mem_ptr), 0x8033143602603b576b58600c8038038082843982f38252388083602039600c01)
            mstore(add(96, solidity_free_mem_ptr), mul(0x601483f0005b8180808030318587f1, 0x10000000000000000000000000000000000))
            root_forwarder := create(0, add(30, solidity_free_mem_ptr), 81)
        }
        return root_forwarder;
    }
    
    function withdrawFromCommitAddress(uint256 bid, uint256 witness) internal returns (bool done) {
        address forwarder;
        (done, forwarder) = _createForwarderAtCommitAddress(bid, witness);
        if (!done) {
            return false;
        }

        if (msg.gas < 20000) {
            return false;
        }

        // Call forwarder with non-empty call data for withdrawal
        assert(forwarder.call(bytes1(1)));

        return true;
    }    

    // ---- (public) helper methods ------------------------------------------
    // TODO(lorenzb):  It would be nicer to make these internal so that they 
    // aren't part of the contract ABI and there is less attack surface for 
    // an attacker.
    // Leaving them public for now to make testing easy.

    // Hacky contract address computation that avoids
    // implementing the full RLP encoding.
    // nonce must be less than 128.
    function _contractAddress(address parent, uint8 nonce) constant returns (address) {
        assert(nonce <= 127);
        if (nonce == 0) {
            nonce = 128;
        }
        return address(keccak256(uint16(0xd694), parent, nonce));
    }

    function _isContract(address addr) constant returns (bool) {
        uint size;
        assembly { 
            size := extcodesize(addr) 
        }
        return size > 0;
    }

    function _commit(uint256 bid, uint256 witness) constant internal returns (uint256) {
        return uint256(keccak256(address(this), msg.sender, bid, witness));
    }

    function _createForwarderAtCommitAddress(uint256 bid, uint256 witness) returns (bool done, address forwarder) {
        uint commit = _commit(bid, witness);
        address account = rootForwarder;
        for (uint i = 0; i < COMMIT_LENGTH / 2; i++) {
            uint8 nonce = uint8(commit % 4) + 1;
            address new_account = _contractAddress(account, nonce);
            while (!_isContract(new_account)) {
                if (msg.gas < cloneMinGas) {
                    return (false, 0);
                }
                assert(account.call());
            }
            account = new_account;
            commit /= 4;
        }
        return (true, account);
    }

    // ---- public methods ---------------------------------------------------

    function commitAddress(uint256 bid, uint256 witness) constant returns (address) {
        uint commit = _commit(bid, witness);
        address account = rootForwarder;
        for (uint i = 0; i < COMMIT_LENGTH / 2; i++) {
            uint8 nonce = uint8(commit % 4) + 1;
            account = _contractAddress(account, nonce);
            commit /= 4;
        }
        return account;
    }

    function checkBid(uint256 bid, uint256 witness) constant returns (bool) {
        address commit_address = commitAddress(bid, witness);
        return commit_address.balance == bid;
    }
   
    // Need to be able to receive funds from Forwarder
    function () payable {
    }

    function revealBid(uint256 bid, uint256 witness) {
        require(startBlock + COMMIT_WINDOW <= block.number);
        require(block.number < startBlock + COMMIT_WINDOW + REVEAL_WINDOW);
        require(checkBid(bid, witness));
        
        if (highestBid < bid) {
            highestBid = bid;
            highestBidder = msg.sender;
        }
    }
    
    // highestBidder becomes winner, Auction contract keeps funds
    function finalizeWinner(uint256 bid, uint256 witness) returns (bool done) {
        require(FINALIZE_MIN_GAS <= msg.gas);
        require(startBlock + COMMIT_WINDOW + REVEAL_WINDOW <= block.number);
        require(msg.sender == highestBidder);
        require(checkBid(bid, witness));

        if (!withdrawFromCommitAddress(bid, witness)) {
            return false;
        }

        if (msg.gas < 20000) {
            return false;
        }        

        winner = highestBidder;
        return true;
    }

    // losers can get their money back from Auction contract
    function finalizeLoser(uint256 bid, uint256 witness) returns (bool done) {
        require(FINALIZE_MIN_GAS <= msg.gas);
        require(startBlock + COMMIT_WINDOW + REVEAL_WINDOW <= block.number);
        require(msg.sender != highestBidder);
        require(checkBid(bid, witness));

        if (!withdrawFromCommitAddress(bid, witness)) {
            return false;
        }

        if (msg.gas < 20000) {
            return false;
        }

        msg.sender.transfer(bid);
        return true;
    }
}