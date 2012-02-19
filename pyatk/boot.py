# Copyright (c) 2012, Harry Bock <bock.harryw@gmail.com>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met: 
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer. 
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution. 
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
Freescale i.MX Serial Boot Protocol implementation
"""
import sys
import array
import struct
import binascii

## More of these are defined depending on the i.MX part and
## installed bootloader. These are all that is needed for
## the i.MX258, as far as we can tell.
CMD_READ_MEMORY     = 0x0101
CMD_WRITE_MEMORY    = 0x0202
CMD_WRITE_FILE      = 0x0404
CMD_GET_STATUS      = 0x0505
CMD_REENUMERATE_USB = 0x0909

DATA_SIZE_BYTE     = 0x08
DATA_SIZE_HALFWORD = 0x10
DATA_SIZE_WORD     = 0x20

#: Terminates serial protocol and runs application.
FILE_TYPE_APPLICATION = 0xAA
#: Secure boot mode only.
FILE_TYPE_CSF         = 0xCC
FILE_TYPE_DCD         = 0xEE

## These are defined in i.MX25 RM table 7-29 (HAB status codes).
#: Successful operation complete.
HAB_PASSED             = 0xF0F0F0F0
#: Failure not matching any other description.
HAB_FAILURE            = 0x39393939
#: Data specified is out of bounds
HAB_DATA_OUT_OF_BOUNDS = 0x8D8D8D8D
#: Error during Assert Verification.
HAB_FAIL_ASSERT        = 0x55555555
#: Write operation to register failed.
HAB_INVALID_WRITE_REG  = 0x66666666

#: Status returned after a write file request is made.
BOOT_PROTOCOL_COMPLETE = 0x88888888

#: Acknowledge word for production-level security parts
ACK_PRODUCTION_PART  = 0x12343412
#: Acknowledge word for engineering-level security parts
ACK_ENGINEERING_PART = 0x56787856
#: Acknolwedge word for successful memory write
ACK_WRITE_SUCCESS    = 0x128A8A12

STATUS_CODE_TABLE = {
    HAB_PASSED: "Successful operation complete",
    HAB_FAILURE: "Failure not matching any other description",
    HAB_DATA_OUT_OF_BOUNDS: "Data specified is out of bounds",
    HAB_FAIL_ASSERT: "Error during Assert Verification",
    HAB_INVALID_WRITE_REG: "Write operation to register failed.",
}

def get_status_string(code):
    """ Given a HAB status code ``code``, return an associated description. """
    return STATUS_CODE_TABLE.get(code, "Unknown code 0x%08x" % code)

class CommandResponseError(Exception):
    def __init__(self, msg):
        super(CommandResponseError, self).__init__()
        self.msg = msg

    def __str__(self):
        return self.msg

class SerialBootProtocol(object):
    def __init__(self, channel, byteorder = 'little'):
        self.channel = channel
        self.byteorder = byteorder

    def _read_status(self):
        status_raw = self.channel.read(4)
        if len(status_raw) != 4:
            raise CommandResponseError("Expected 4-byte status word, "
                                       "got %r (%r) instead" % (status_raw,
                                                                binascii.hexlify(status_raw)))

        return struct.unpack("<I", status_raw)[0]

    def _read_ack(self):
        ack = self._read_status()
        if ack not in (ACK_PRODUCTION_PART, ACK_ENGINEERING_PART):
            raise CommandResponseError("Received unexpected status code instead "
                                       "of ACK: 0x%08X" % ack)
    
    def _write_command(self, command):
        """
        Write serial bootloader command string ``command``,
        automatically padded to 16 bytes.
        """
        # Pad command to 16 bytes
        if len(command) < 16:
            command += "\x00" * (16 - len(command))

        self.channel.write(command)

    def get_status(self):
        """
        Query for and return the ROM status.
        """
        command = struct.pack(">H", CMD_GET_STATUS)
        self._write_command(command)
        return self._read_status()

    def read_memory(self, address, datasize, length = 1):
        """
        Read memory at ``address``.  Read ``length`` successive
        addresses of width ``datasize``.

        If ``length`` is 1, return an integer with the value read
        from memory.  If ``length`` is greater than 1, return
        an array of values read sequentially from memory.

        All values are converted from CPU byte order to host byte
        order.
        """
        if datasize not in (DATA_SIZE_BYTE,
                            DATA_SIZE_HALFWORD,
                            DATA_SIZE_WORD):
            raise ValueError("Invalid data size")

        if address < 0 or address > 0xffffffff:
            raise ValueError("Invalid address")

        command = struct.pack(">HIBI", CMD_READ_MEMORY, address, datasize, length)
        self._write_command(command)

        # Receive 4-byte ACK
        ack = self._read_ack()

        if datasize == DATA_SIZE_BYTE:
            typecode = "B"
        elif datasize == DATA_SIZE_HALFWORD:
            typecode = "H"
        elif datasize == DATA_SIZE_WORD:
            typecode = "I"
        # convert to byte width
        datasize = datasize / 8
        
        retarray = array.array(typecode)

        # Get variable-length data
        for i in xrange(length):
            data = self.channel.read(datasize)
            if len(data) != datasize:
                raise CommandResponseError("Data received is of invalid length")

            retarray.fromstring(data)

        # You send things MSB first, but get them back in processor order.
        if self.byteorder != sys.byteorder:
            retarray.byteswap()

        if length == 1:
            return retarray[0]
        else:
            return retarray

    def write_memory(self, address, datasize, data):
        if datasize not in (DATA_SIZE_BYTE,
                            DATA_SIZE_HALFWORD,
                            DATA_SIZE_WORD):
            raise ValueError("Invalid data size")

        if address < 0 or address > 0xffffffff:
            raise ValueError("Invalid address")

        command = struct.pack(">HIB4x", CMD_WRITE_MEMORY, address, datasize)
        
        if datasize == DATA_SIZE_BYTE:
            command += struct.pack(">3xB", data)
        elif datasize == DATA_SIZE_HALFWORD:
            command += struct.pack(">2xH", data)
        elif datasize == DATA_SIZE_WORD:
            command += struct.pack(">I", data)

        self._write_command(command)

        ack = self._read_ack()

        # Read write acknowledge code (ACK_WRITE_SUCCESS)
        try:
            ack = self._read_status()

        # If we don't get enough bytes back, a write failure occured.
        # Why doesn't the protocol just send back an error response?
        except CommandResponseError:
            raise CommandResponseError("Write memory failed!")

        # The i.MX25 manual lies.  This is the SUCCESS ACK! The error
        # acknowledge is no response after 0x56787856, but the manual
        # says it's the other way around...
        if ack == ACK_WRITE_SUCCESS:
            return True

        else:
            raise CommandResponseError("Received unexpected status instead "
                                       "of ACK: 0x%08X" % ack)
        
    def write_file(self, filetype, address, length, stream):
        command = struct.pack(">HIxI4xB", CMD_WRITE_FILE, address, length, filetype)
        self._write_command(command)
        self._read_ack()

        bytes_consumed = 0
        chunk_size = 1024

        while bytes_consumed < length:
            chunk = stream.read(chunk_size)
            if chunk == "":
                raise ValueError("File stream ends early after %u "
                                 "bytes consumed." % bytes_consumed)
            bytes_consumed += len(chunk)
            self.channel.write(chunk)

    def reenumerate_usb(self, serialnum):
        """
        Force re-enumeration of USB PHY with serial number ``serialnum``
        """
        if len(serialnum) != 4:
            raise ValueError("Invalid serial number")

        command = struct.pack(">H7x4s", CMD_REENUMERATE_USB, serialnum)
        self._write_command(command)
        resp = self.channel.read(4)
        if resp != "\x89\x23\x23\x89":
            raise CommandResponseError("Invalid re-enumerate response: %r" % resp)

    def complete_boot(self):
        """
        This must be called immediately after calling :meth:`write_file` with file type
        :const:`FILE_TYPE_APPLICATION`.  This will execute the application starting
        at the specified start address.
        """
        # You can write anything, as long as it's 16 bytes, and it will
        # move along the boot process.
        status = self.get_status()

        if status != BOOT_PROTOCOL_COMPLETE:
            raise CommandResponseError("Expected boot protocol completion code 0x88888888, "
                                       ", got 0x%08X instead!" % status)

        return status
