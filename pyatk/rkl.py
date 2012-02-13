"""
Freescale i.MX ATK RAM kernel protocol implementation
"""
# (c) 2012 Harry Bock <bock.harryw@gmail.com>

import struct
import binascii

HEADER_MAGIC = 0x0606

## RKL NAND flash commands
CMD_FLASH_INITIAL      = 0x0001
CMD_FLASH_ERASE        = 0x0002
CMD_FLASH_DUMP         = 0x0003
CMD_FLASH_PROGRAM      = 0x0004
CMD_FLASH_PROGRAM_UB   = 0x0005
CMD_FLASH_GET_CAPACITY = 0x0006

## RKL eFUSE commands
CMD_FUSE_READ     = 0x0101
CMD_FUSE_SENSE    = 0x0102
CMD_FUSE_OVERRIDE = 0x0103
CMD_FUSE_PROGRAM  = 0x0104

## RKL common commands
CMD_RESET    = 0x0201
CMD_DOWNLOAD = 0x0202
CMD_EXECUTE  = 0x0203
CMD_GETVER   = 0x0204

## Extended commands
CMD_COM2USB  = 0x0301
CMD_SWAP_BI  = 0x0302
CMD_FL_BBT   = 0x0303
CMD_FL_INTLV = 0x0304
CMD_FL_LBA   = 0x0305

ACK_SUCCESS = 0x0000
ACK_FAILED  = 0xffff

class CommandResponseError(Exception):
    def __init__(self, command, ackcode):
        super(CommandResponseError, self).__init__()
        #: Command code that generated this error.
        self.command = command
        #: Response code from the device.
        self.ack = ackcode

    def __str__(self):
        return "Command 0x%04X failed: ack code 0x%04X" % (self.command, self.ack)

class RAMKernelProtocol(object):
    def __init__(self, channel):
        self.channel = channel

    def _send_command(self, command,
                      address = 0x00000000,
                      param1  = 0x00000000,
                      param2  = 0x00000000,
                      wait_for_response = True):
        rawcmd = struct.pack(">HHIII", HEADER_MAGIC, command, address, param1, param2)
        self.channel.write(rawcmd)

        if wait_for_response:
            response = self.channel.read(8)
            ack, checksum, length = struct.unpack(">HHI", response)
            if length > 0:
                payload = self.channel.read(length)
            else:
                payload = ""

            if ack != ACK_SUCCESS:
                raise CommandResponseError(command, ack)

            return checksum, payload

    def getver(self):
        imx_type, flash_model = self._send_command(CMD_GETVER)
        print "imx, flash model =", imx_type, repr(flash_model)

    def reset(self):
        self._send_command(CMD_RESET, wait_for_response = False)
