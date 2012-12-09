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
