import unittest

from ethereum.tools import tester as t
from ethereum.utils import mk_contract_address, checksum_encode

AUCTION_CONTRACT = 'contract/auction.sol'

class TestAuction(unittest.TestCase):
    def null_address(self):
        return '0x' + '0' * 40

    def assertEqualAddr(self, *args, **kwargs):
        return self.assertEqual(checksum_encode(args[0]), checksum_encode(args[1]), *args[2:], **kwargs)

    def setUp(self):
        self.chain = t.Chain()

        self.chain.mine(number_of_blocks=2)

        with open(AUCTION_CONTRACT, 'r') as f:
            code = f.read()
        self.auction_contract = self.chain.contract(
            code, language='solidity', value=0, startgas=10**6)

    def test_initial_state(self):
        ac = self.auction_contract
        self.assertGreater(ac.cloneMinGas(), 1e4)
        self.assertLess(ac.cloneMinGas(), 1e6)
        self.assertEqual(self.null_address(), ac.highestBidder())
        self.assertEqual(0, ac.highestBid())
        self.assertEqual(self.null_address(), ac.winner())
        self.assertEqual(3, ac.startBlock())

    def test_finalizeMinGas(self):
        ac = self.auction_contract
        self.assertGreater(ac.FINALIZE_MIN_GAS(), 5 * ac.cloneMinGas())

    def test_contractAddress(self):
        ac = self.auction_contract
        addresses = [
            self.null_address(),
            '0x' + 'f' * 40,
            '0x' + '0' * 20 + 'a' * 20,
            '0x' + 'a' * 20 + '0' * 20,
            '0xEA674fdDe714fd979de3EdF0F56AA9716B898ec8',
        ]
        for address in addresses:
            for i in range(128):
                self.assertEqualAddr(mk_contract_address(address, i), ac._contractAddress(address, i))

        with self.assertRaises(t.TransactionFailed):
            ac._contractAddress('0xEA674fdDe714fd979de3EdF0F56AA9716B898ec8', 128)

    def test_isContract(self):
        ac = self.auction_contract
        self.assertTrue(ac._isContract(ac.address))
        self.assertFalse(ac._isContract('0xEA674fdDe714fd979de3EdF0F56AA9716B898ec8'))
        self.assertFalse(ac._isContract(t.a0))

    def test_checkBid(self):
        ac = self.auction_contract
        val0, wit0 = 1, 2**256-1

        self.assertFalse(ac.checkBid(val0, wit0))

        addr0 = ac.commitAddress(val0, wit0, sender=t.k0)
        self.chain.tx(sender=t.k0, to=addr0, value=val0)

        self.assertTrue(ac.checkBid(val0, wit0))
        self.assertFalse(ac.checkBid(val0 + 1, wit0))
        self.assertFalse(ac.checkBid(val0, wit0 - 1))
        self.assertFalse(ac.checkBid(val0, wit0, sender=t.k1))

    def test_createForwarderAtCommitAddress_basic(self):
        ac = self.auction_contract
        self.chain.mine(number_of_blocks=1)
        done, addr = ac._createForwarderAtCommitAddress(174, 9872, startgas=4000000)
        self.assertFalse(done)
        self.assertEqual(self.null_address(), addr)
        self.chain.mine()
        done, addr = ac._createForwarderAtCommitAddress(174, 9872, startgas=4000000)
        self.assertTrue(done)

    def test_createForwarderAtCommitAddress_mingas(self):
        ac = self.auction_contract
        for i in range(20):
            done, addr = ac._createForwarderAtCommitAddress(174, 9872, startgas=ac.FINALIZE_MIN_GAS())
            self.chain.mine()
            if done: break
        else:
            self.fail("cloneMinGas too small")


    def test_commitAddressEqCreateForwarderAtCommitAddress(self):
        ac = self.auction_contract

        addr0 = ac.commitAddress(937, 11)

        self.chain.mine()

        done, _ = ac._createForwarderAtCommitAddress(937, 11, startgas=4300000)
        self.assertFalse(done)

        self.chain.mine()

        done, addr1 = ac._createForwarderAtCommitAddress(937, 11, startgas=4300000)
        self.assertTrue(done)
        self.assertEqual(addr0, addr1)

    def test_revealBid_wrong(self):
        ac = self.auction_contract
        addr0 = ac.commitAddress(7, 13371337)
        self.chain.tx(sender=t.k0, to=addr0, value=6)
        self.chain.mine()
        # too early
        with self.assertRaises(t.TransactionFailed):
            ac.revealBid(7, 13371337, sender=t.k0)

        self.chain.mine(number_of_blocks=ac.COMMIT_WINDOW())

        # amount differs from commit
        with self.assertRaises(t.TransactionFailed):
            ac.revealBid(6, 13371337)
        self.chain.mine()

        # amount differs from account balance
        with self.assertRaises(t.TransactionFailed):
            ac.revealBid(7, 13371337)

    def test_auction(self):
        ac = self.auction_contract
        val0, wit0 = 5 * 10**15, 1321
        val1, wit1 = 7 * 10**15, 86413
        val2, wit2 = 6 * 10**15, 93764312
        addr0 = ac.commitAddress(val0, wit0, sender=t.k0)
        addr1 = ac.commitAddress(val1, wit1, sender=t.k1)
        addr2 = ac.commitAddress(val2, wit2, sender=t.k2)
        self.chain.tx(sender=t.k0, to=addr0, value=val0)
        self.chain.tx(sender=t.k1, to=addr1, value=val1)
        self.chain.tx(sender=t.k2, to=addr2, value=val2)

        self.chain.mine(number_of_blocks=ac.COMMIT_WINDOW())

        self.assertTrue(ac.checkBid(val0, wit0, sender=t.k0))
        self.assertTrue(ac.checkBid(val1, wit1, sender=t.k1))
        self.assertTrue(ac.checkBid(val2, wit2, sender=t.k2))

        ac.revealBid(val0, wit0, sender=t.k0)
        self.assertEqual(val0, ac.highestBid())
        self.assertEqualAddr(t.a0, ac.highestBidder())

        ac.revealBid(val1, wit1, sender=t.k1)
        self.assertEqual(val1, ac.highestBid())
        self.assertEqualAddr(t.a1, ac.highestBidder())

        ac.revealBid(val2, wit2, sender=t.k2)
        self.assertEqual(val1, ac.highestBid())
        self.assertEqualAddr(t.a1, ac.highestBidder())

        # too early
        with self.assertRaises(t.TransactionFailed):
            ac.finalizeWinner(val1, wit1, sender=t.k1, startgas=3700000)


        self.chain.mine(number_of_blocks=ac.REVEAL_WINDOW())

        self.assertFalse(ac.finalizeLoser(val0, wit0, sender=t.k0, startgas=3700000))
        self.chain.mine()
        self.assertTrue(ac.finalizeLoser(val0, wit0, sender=t.k0, startgas=3700000))
        self.chain.mine()
        self.assertEqual(
            self.chain.head_state.get_balance(addr0), 0)

        # loser cannot finalize twice
        with self.assertRaises(t.TransactionFailed):
            ac.finalizeLoser(val0, wit0, sender=t.k0, startgas=3700000)
        self.chain.mine()

        # winner cannot finalize as loser
        with self.assertRaises(t.TransactionFailed):
            ac.finalizeLoser(val1, wit1, sender=t.k1, startgas=3700000)
        self.chain.mine()

        # loser cannot finalize as winner
        with self.assertRaises(t.TransactionFailed):
            ac.finalizeWinner(val2, wit2, sender=t.k2, startgas=3700000)
        self.chain.mine()

        # winner cannot finalize with too low gas
        with self.assertRaises(t.TransactionFailed):
            ac.finalizeWinner(val1, wit1, sender=t.k1, startgas=300000)
        self.chain.mine()

        self.assertEqualAddr(self.null_address(), ac.winner())
        self.assertTrue(ac.checkBid(val1, wit1, sender=t.k1))
        self.assertFalse(ac.finalizeWinner(val1, wit1, sender=t.k1, startgas=3700000))
        self.chain.mine()
        self.assertTrue(ac.finalizeWinner(val1, wit1, sender=t.k1, startgas=3700000))
        self.chain.mine()
        self.assertEqual(
            self.chain.head_state.get_balance(addr1), 0)
        self.assertEqual(
            self.chain.head_state.get_balance(ac.address), val1)
        self.assertEqualAddr(t.a1, ac.winner())

        # winner cannot finalize twice
        with self.assertRaises(t.TransactionFailed):
            ac.finalizeWinner(val1, wit1, sender=t.k1, startgas=3700000)
        self.chain.mine()

        # loser cannot finalize with too low gas
        with self.assertRaises(t.TransactionFailed):
            ac.finalizeLoser(val2, wit2, sender=t.k2, startgas=300000)
        self.chain.mine()

        self.assertFalse(ac.finalizeLoser(val2, wit2, sender=t.k2, startgas=3700000))
        self.chain.mine()
        self.assertTrue(ac.finalizeLoser(val2, wit2, sender=t.k2, startgas=3700000))
        self.chain.mine()
        self.assertEqual(
            self.chain.head_state.get_balance(addr2), 0)
        self.assertEqual(
            self.chain.head_state.get_balance(ac.address), val1)
        self.assertEqualAddr(t.a1, ac.winner())

if __name__ == '__main__':
    unittest.main()
