import sys
import array
import unittest
import struct

from pyatk.tests.mockchannel import MockChannel
from pyatk import boot

class SerialBootProtocolTests(unittest.TestCase):
    def setUp(self):
        self.channel = MockChannel()
        self.sbp = boot.SerialBootProtocol(self.channel)

    def test_get_status_string(self):
        self.assertEqual("Successful operation complete",
                         boot.get_status_string(boot.HAB_PASSED))

        self.assertEqual("Failure not matching any other description",
                         boot.get_status_string(boot.HAB_FAILURE))

        self.assertEqual("Unknown code 0x5643beef",
                         boot.get_status_string(0x5643BEEF))


    def queue_sbp_resp(self, resp):
        self.channel.queue_data(struct.pack(">I", resp))

    def queue_ack_prod(self):
        self.queue_sbp_resp(boot.ACK_PRODUCTION_PART)

    def queue_ack_eng(self):
        self.queue_sbp_resp(boot.ACK_ENGINEERING_PART)

    def test_get_status(self):
        """ Test decoding SBP status """
        self.channel.queue_data(b"\xff\xff\xff\xff")
        status = self.sbp.get_status()
        self.assertEqual(0xffffffff, status)

        self.channel.queue_data(b"\xef\xbe\xad\xde")
        status = self.sbp.get_status()
        self.assertEqual(0xdeadbeef, status)

    def test_read_memory_invalid_address_size(self):
        """
        Test raising ValueError on calling read_memory() with invalid address
        and/or access width.
        """
        for address, datasize in (
            (-1, boot.DATA_SIZE_BYTE),
            (0, 99),
            (0xffffffff + 1, boot.DATA_SIZE_WORD),
        ):
            self.assertRaises(ValueError, self.sbp.read_memory, address, datasize)

    def test_read_memory_halfword(self):
        """ Test basic functionality of read_memory(). """
        # Queue up the response
        self.queue_ack_eng()
        self.channel.queue_data("\xaa\xbb")

        ret = self.sbp.read_memory(0x25, boot.DATA_SIZE_HALFWORD, 1)
        # Ensure we get an array of the correct type with the correctly byte-swapped
        # value.
        self.assertEqual(array.array('H', [0xbbaa]), ret)
        # Ensure we send the correct command data, aligned to 16 bytes.
        self.assertEqual(b"\x01\x01\x00\x00\x00\x25\x10\x00\x00\x00\x01\x00\x00\x00\x00\x00",
                         self.channel.get_data_written())

    def test_read_memory_word_multiple(self):
        """ Test basic functionality of read_memory(). """
        # Queue up the response
        self.queue_ack_eng()
        self.channel.queue_data("\x01\x00\x00\x00\x02\x00\x00\x00")

        ret = self.sbp.read_memory(0x99, boot.DATA_SIZE_WORD, 2)
        # Ensure we get an array of the correct type with the correctly byte-swapped
        # value.
        self.assertEqual(array.array('I', [1, 2]), ret)
        # Ensure we send the correct command data, aligned to 16 bytes.
        self.assertEqual(b"\x01\x01\x00\x00\x00\x99\x20\x00\x00\x00\x02\x00\x00\x00\x00\x00",
                         self.channel.get_data_written())

    def test_read_memory_word_multiple_byteswap(self):
        """ Test basic functionality of read_memory() with byte swapping. """
        self.queue_ack_eng()

        # Switch processor byte order to the opposite byte order of
        # the host system to ensure we need to byte swap
        if "little" == sys.byteorder:
            self.sbp.byteorder = "big"
            self.channel.queue_data("\x00\x00\x00\x01\x00\x00\x00\x02")
        else:
            self.sbp.byteorder = "little"
            self.channel.queue_data("\x01\x00\x00\x00\x02\x00\x00\x00")

        ret = self.sbp.read_memory(0x99, boot.DATA_SIZE_WORD, 2)
        # Ensure we get an array of the correct type with the correctly byte-swapped
        # value.
        self.assertEqual(array.array('I', [1, 2]), ret)
        # Ensure we send the correct command data, aligned to 16 bytes.
        self.assertEqual(b"\x01\x01\x00\x00\x00\x99\x20\x00\x00\x00\x02\x00\x00\x00\x00\x00",
                         self.channel.get_data_written())

    def test_read_memory_short_response(self):
        """ Test error functionality of read_memory() with not enough data read. """
        self.queue_ack_eng()
        self.assertRaises(boot.CommandResponseError,
                          self.sbp.read_memory, 0x99, boot.DATA_SIZE_WORD, 2)

    def test_read_memory_single(self):
        """ Test basic functionality of read_memory(). """
        # Queue up the response
        self.queue_ack_eng()
        self.channel.queue_data("\xaa\xbb")

        ret = self.sbp.read_memory_single(0x25, boot.DATA_SIZE_HALFWORD)
        # Ensure we get an array of the correct type with the correctly byte-swapped
        # value.
        self.assertEqual(0xbbaa, ret)
        # Ensure we send the correct command data, aligned to 16 bytes.
        self.assertEqual(b"\x01\x01\x00\x00\x00\x25\x10\x00\x00\x00\x01\x00\x00\x00\x00\x00",
                         self.channel.get_data_written())

    def test_complete_boot(self):
        """ Test the Completed command for the serial boot protocol. """
        self.queue_sbp_resp(boot.BOOT_PROTOCOL_COMPLETE)
        self.assertEqual(boot.BOOT_PROTOCOL_COMPLETE, self.sbp._complete_boot())

        # Doesn't matter what was written, as long as it is 16 bytes!
        self.assertEqual(16, len(self.channel.get_data_written()))

    def test_complete_boot_bad_response(self):
        """ Test the Completed command for the serial boot protocol. """
        self.queue_sbp_resp(boot.HAB_PASSED)
        self.assertRaises(boot.CommandResponseError, self.sbp._complete_boot)

        # Doesn't matter what was written, as long as it is 16 bytes!
        self.assertEqual(16, len(self.channel.get_data_written()))

    def test_write_memory_byte(self):
        # Queue ACK_ENGINEERING_PART
        self.queue_ack_eng()
        # Queue ACK_WRITE
        self.queue_sbp_resp(boot.ACK_WRITE_SUCCESS)
        self.sbp.write_memory(0xbeefcafe, boot.DATA_SIZE_BYTE, 0x01)
        self.assertEqual(b"\x02\x02\xbe\xef\xca\xfe\x08\x00\x00\x00\x00\x00\x00\x00\x01\x00",
                         self.channel.get_data_written())

    def test_write_memory_halfword(self):
        # Queue ACK_ENGINEERING_PART
        self.queue_ack_eng()
        # Queue ACK_WRITE
        self.queue_sbp_resp(boot.ACK_WRITE_SUCCESS)
        self.sbp.write_memory(0xbeefcafe, boot.DATA_SIZE_HALFWORD, 0xfeed)
        self.assertEqual(b"\x02\x02\xbe\xef\xca\xfe\x10\x00\x00\x00\x00\x00\x00\xfe\xed\x00",
                         self.channel.get_data_written())

    def test_write_memory_word(self):
        # Queue ACK_ENGINEERING_PART
        self.queue_ack_eng()
        # Queue ACK_WRITE
        self.queue_sbp_resp(boot.ACK_WRITE_SUCCESS)
        self.sbp.write_memory(0xbeefcafe, boot.DATA_SIZE_WORD, 0xcafefeed)
        self.assertEqual(b"\x02\x02\xbe\xef\xca\xfe\x20\x00\x00\x00\x00\xca\xfe\xfe\xed\x00",
                         self.channel.get_data_written())