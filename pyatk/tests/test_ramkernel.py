import unittest

from pyatk.channel.mock import MockChannel
from pyatk import ramkernel

class RAMKernelTests(unittest.TestCase):
    def setUp(self):
        self.channel = MockChannel()
        self.rkl = ramkernel.RAMKernelProtocol(self.channel)

    def test_flash_init_error(self):
        self.channel.queue_rkl_response(ramkernel.FLASH_ERROR_INIT, 0, 0)
        with self.assertRaises(ramkernel.CommandResponseError) as cm:
            self.rkl.flash_initial()

        self.assertEqual(cm.exception.ack, ramkernel.FLASH_ERROR_INIT)
        self.assertEqual(cm.exception.command, ramkernel.CMD_FLASH_INITIAL)
        self.assertEqual(cm.exception.payload_or_length, "")

    def test_flash_get_capacity(self):
        self.channel.queue_rkl_response(ramkernel.ACK_SUCCESS, 0xbeef, 2057)
        self.assertEqual(self.rkl.flash_get_capacity(), 2057)
        self.channel.queue_rkl_response(ramkernel.ACK_SUCCESS, 0xbeef, 0x1FFFF)
        self.assertEqual(self.rkl.flash_get_capacity(), 0x1FFFF)

    def test_getver(self):
        # Test CMD_GETVER responses of various shapes and sizes, including
        # with payloads containing non-ASCII data.
        for imx_version, flash_model in (
            (0xface, "HAL 9000"),
            (0xbeef, "Taste the biscuit"),
            (0x2057, "Silly rabbit Freescale's for kids"),
            (0xfeed, "So I should \x1bprobably sleep\xAF\x99 at some point \x00tonight"),
        ):
            self.channel.queue_rkl_response(ramkernel.ACK_SUCCESS, imx_version,
                                            len(flash_model), flash_model)

            ver, flash = self.rkl.getver()
            self.assertEqual(ver, imx_version)
            self.assertEqual(flash, flash_model)

    def test_erase(self):
        """ Test the flash_erase API with no callback specified. """
        block_size = 0x20000

        for block_index in xrange(50):
            self.channel.queue_rkl_response(ramkernel.ACK_FLASH_ERASE, block_index, block_size)
        self.channel.queue_rkl_response(ramkernel.ACK_SUCCESS, 0, 0)

        self.rkl.flash_erase(0x0, 1)

    def test_erase_callback(self):
        """ Test flash_erase with erase_callback specified. """
        callback_data = []
        block_size = 0x20000

        # Queue 50 block erase responses, each with a different block size.
        # Generally the block size returned by RKL is fixed, but if it is not,
        # we should be sending the right value.
        for block_index in xrange(50):
            self.channel.queue_rkl_response(ramkernel.ACK_FLASH_ERASE,
                                            block_index,
                                            block_size + block_index)
        self.channel.queue_rkl_response(ramkernel.ACK_SUCCESS, 0, 0)

        # Close over callback_data to make sure it is called correctly.
        def erase_cb(block_idx, block_sz):
            callback_data.append((block_idx, block_sz))

        # Flash erase doesn't care how many bytes you specify, or the start address.
        # We're just testing how it handles RKL proto responses.
        self.rkl.flash_erase(0x0, 1, erase_callback=erase_cb)

        self.assertEqual(len(callback_data), 50)
        for index, (cb_block_idx, cb_block_sz) in zip(xrange(50), callback_data):
            self.assertEqual(cb_block_idx, index)
            self.assertEqual(cb_block_sz, block_size + index)



