# A PoC for Submarine Sends

This repo contains a proof-of-concept implementation of Submarine Sends for
Ethereum as described in the blog post ["To Sink Frontrunners, Send in the
Submarines"](http://hackingdistributed.com/2017/08/28/submarine-sends/) by
Lorenz Breidenbach, Phil Daian, Ari Juels, and Florian Tramèr.

## Disclaimer

**This is a proof-of-concept implementation written for research purposes. The
code has not been audited and may contain bugs or security vulnerabilities.**

In particular, the code does currently not support Merkle-Patricia-proofs; a
potential adversary could frontrun reveals until these are implemented.

## Requirements

To run the tests in this repo, you will need

- a recent version of the Solidity compiler `solc`: Consult the [solidity
  docs](http://solidity.readthedocs.io/en/develop/installing-solidity.html) for
  installation instructions.
- `python` >= 3.6 (for pyethereum) and `pip`

If you want to assemble the EVM assembly files, you will also need the `evm`
tool which is a part of [go-ethereum](https://github.com/ethereum/go-ethereum).

You should then be able to install any dependencies by running
```
pip3 install -r requirements.txt
```

## Organization

The `contract/` directory contains three contracts:

- `auction.sol` is an example of a simple sealed-bid auction contract that makes
  use of Submarine Sends. Here is how it works:
    - The auction starts when the contract is created. Participants have
      `COMMIT_WINDOW` blocks to place a bid.
    - To place a bid, a participant calls `commitAddress` passing in the desired
      `bid` amount (in Wei) and a randomly chosen 256-bit `witness` and sends
      `bid` Wei to the returned address.
    - Once `COMMIT_WINDOW` blocks have passed since the creation of the auction
      contract, a participant should reveal her bid by calling `revealBid` with
      the same `bid` and `witness` passed to `commitAddress`. Unrevealed bids
      remain locked up forever!
    - Once `REVEAL_WINDOW` blocks have passed since the end of the commit
      window, no more reveals are accepted. Participants can use `highestBidder`
      to check whether they won the auction. The highest bidder should call
      `finalizeWinner` to be officially acknowledged as the `winner` of the
      auction. Everybody else should call `finalizeLoser` to receive a refund
      for their bids.
    - `finalizeWinner` and `finalizeLoser` have a high gas cost because they
      need to create many contracts. To successfully call them, you need to pass
      in at least `FINALIZE_MIN_GAS` gas (this is to ensure progress). Since
      finalization may cost too much gas to fit into a single block, you may
      have to repeatedly call `finalize*` until it returns `true` to indicate
      that it is done.
- `forwarder.easm` contains EVM assembly code for a forwarder contract that
  allows its owner to withdraw funds and anybody to create further clones of the
  contract.
- `initcode_header.easm` contains EVM assembly initcode that can be prepended to
  any contracts code (assuming that the contract doesn't need storage
  initialization).

`test/` is for tests:
- `test_auction.py` contains the test-suite for `auction.sol`.

## Running tests

The `auction.sol` contract has a test-suite. You can run it like this:
```
python3.6 -m test.test_auction
```

## Working with `easm` files

To assemble/compile `foo.easm`, simply run
```
evm compile foo.easm
```
