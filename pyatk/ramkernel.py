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
Freescale i.MX ATK RAM kernel protocol implementation
"""
import struct

HEADER_MAGIC = 0x0606

## RKL NAND flash commands
CMD_FLASH_INITIAL      = 0x0001
CMD_FLASH_ERASE        = 0x0002
CMD_FLASH_DUMP         = 0x0003
CMD_FLASH_PROGRAM      = 0x0004
CMD_FLASH_PROGRAM_UB   = 0x0005
CMD_FLASH_GET_CAPACITY = 0x0006

#: Normal (raw) file format for flash programming.
FLASH_FILE_FORMAT_NORMAL = 0
FLASH_FILE_FORMAT_NB0    = 1
FLASH_FILE_FORMAT_OPS    = 2

FLASH_PROGRAM_PARAM1_VERIFY = 0x00010000
FLASH_PROGRAM_PARAM1_GO_ON  = 0x00000100

# The default RAM kernel has an internal buffer of 2 MB.
# CMD_FLASH_PROGRAM(_UB) requests larger than this size
# will fail.
FLASH_PROGRAM_MAX_WRITE_SIZE = (2 * 1024 * 1024)

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

ACK_SUCCESS      = 0x0000
#: We received a partial response for a flash command.
ACK_FLASH_PARTLY = 0x0001
#: We received an erase response for flash
ACK_FLASH_ERASE  = 0x0002
#: We received a verify response for flash
ACK_FLASH_VERIFY = 0x0003
ACK_FAILED       = 0xffff

## Flash operation status codes
FLASH_OK               = 0
FLASH_FAILED           = -4
FLASH_ECC_FAILED       = -5
FLASH_ERROR_READ       = -100
FLASH_ERROR_ECC        = -101
FLASH_ERROR_PROG       = -102
FLASH_ERROR_ERASE      = -103
FLASH_ERROR_VERIFY     = -104
FLASH_ERROR_INIT       = -105
FLASH_ERROR_OVER_ADDR  = -106
FLASH_ERROR_PART_ERASE = -107
FLASH_ERROR_EOF        = -108

_ACK_STR_MAP = {
    # These are not errors
    ACK_SUCCESS:            "no error",
    ACK_FLASH_PARTLY:       "in-progress flash operation",
    ACK_FLASH_ERASE:        "in-progress flash erase",
    ACK_FLASH_VERIFY:       "in-progress flash verify",

    ACK_FAILED:             "general failure",

    # These errors are specific to flash
    FLASH_FAILED:           "flash operation failure",
    FLASH_ECC_FAILED:       "flash ECC failure",
    FLASH_ERROR_READ:       "error reading flash",
    FLASH_ERROR_ECC:        "uncorrectable ECC error",
    FLASH_ERROR_PROG:       "error programming flash",
    FLASH_ERROR_ERASE:      "error erasing flash",
    FLASH_ERROR_VERIFY:     "error verifying flash",
    FLASH_ERROR_INIT:       "error initializing flash part",
    FLASH_ERROR_OVER_ADDR:  "flash address overflow",
    FLASH_ERROR_PART_ERASE: "flash partial erase error: potential bad block(s)",
    FLASH_ERROR_EOF:        "attempt to access flash part past device capacity",
}

def rkl_strerror(ackcode):
    """ Return a string corresponding to RAM kernel ACK code ``code``. """
    return _ACK_STR_MAP.get(ackcode, "unknown error code")

class RAMKernelError(Exception):
    """
    A generic RAM kernel error.
    """
    pass

class ChecksumError(RAMKernelError):
    """
    An error representing a checksum error has occured when reading data
    from the RAM kernel.
    """
    def __init__(self, expected_checksum, checksum):
        super(ChecksumError, self).__init__()
        #: The checksum returned by the device.
        self.expected_checksum = expected_checksum
        #: The checksum calculated on the host.
        self.checksum = checksum

    def __str__(self):
        return "Expected checksum 0x%04X, calculated 0x%04X" % (self.expected_checksum,
                                                                self.checksum)

class CommandResponseError(RAMKernelError):
    """
    An exception representing an error response from the RAM kernel.
    """
    def __init__(self, command, ackcode, length):
        super(CommandResponseError, self).__init__()
        #: Command code that generated this error.
        self.command = command
        #: Response code from the device.
        self.ack = ackcode
        #: Human-readable version of ACK code.
        self.ack_str = rkl_strerror(ackcode)
        #: Payload (if any) or length parameter following ACK
        self.length = length

    def __str__(self):
        return "Command 0x%04X failed: ack code 0x%04X (%s)" % (self.command, self.ack, self.ack_str)

def calculate_checksum(buf):
    """ Perform a simple 16-bit checksum on the bytes in ``buf``. """
    checksum = 0
    for byte in buf:
        checksum = (checksum + ord(byte)) & 0x0000FFFF

    return checksum

class RAMKernelProtocol(object):
    """
    Implementation of the host side of the i.MX RAM kernel protocol.  It is used
    for BSP-specific handling of device flash (MMC, NAND, NOR, etc.) and programmable fuses.
    """
    def __init__(self, channel):
        """
        Create a RAM kernel protocol handler for communications ``channel`` (an instance
        of a :class:`~.ATKChannelI` derivative).
        """
        self.channel = channel

    def _read_response(self):
        """
        Read the device response and return
        """
        response = self.channel.read(8)

        ack, checksum, length = struct.unpack(">hHI", response)
        return ack, checksum, length
        
    def _send_command(self, command,
                      address = 0x00000000,
                      param1  = 0x00000000,
                      param2  = 0x00000000,
                      wait_for_response = True):
        rawcmd = struct.pack(">HHIII", HEADER_MAGIC, command, address, param1, param2)
        self.channel.write(rawcmd)

        if wait_for_response:
            ack, checksum, length = self._read_response()
            if ack not in (ACK_SUCCESS, ACK_FLASH_PARTLY):
                raise CommandResponseError(command, ack, length)

            return ack, checksum, length

    def getver(self):
        """
        Query the RAM kernel for device type and flash model.

        Returns the tuple ``device_type``, ``flash_model``, with
        ``device_type`` a 16-bit integer representing the device and
        ``flash_model`` a string describing the flash model.

        Must be called *after* :meth:`flash_initial`!
        """
        _, checksum, length = self._send_command(CMD_GETVER)
        if length > 0:
            payload = self.channel.read(length)
        else:
            payload = ""

        return checksum, payload

    def flash_initial(self):
        """
        Initialize the device flash subsystem. This **must** be called prior
        to any other ``flash_`` method, as well as prior to :meth:`getver`!
        """
        self._send_command(CMD_FLASH_INITIAL)

    def flash_dump(self, address, size):
        """
        Dump ``size`` bytes of flash starting at address
        ``address``. Returns a string containing at most ``size``
        bytes of flash data.

        Must be called *after* :meth:`flash_initial`!
        """
        payload_list = []
        def read_payload(length):
            # Even if the response was failure, read any additional
            # data queued up.
            if length > 0:
                payload = self.channel.read(length)
            else:
                payload = ""

            mychecksum = calculate_checksum(payload)
            if mychecksum != checksum:
                raise ChecksumError(checksum, mychecksum)

            payload_list.append(payload)
            return len(payload)

        ack, checksum, length = self._send_command(CMD_FLASH_DUMP,
                                                   address = address,
                                                   param1 = size,
                                                   param2 = 0, # follow-up dump (?)
                                                   )
        total_bytes = read_payload(length)

        # If we receive an ACK_FLASH_PARTLY, we are expected to continue
        # reading command responses until we run out of space.
        while total_bytes < size:
            ack, checksum, length = self._read_response()
            if ack != ACK_FLASH_PARTLY:
                raise CommandResponseError(CMD_FLASH_DUMP, ack, length)

            total_bytes += read_payload(length)

        return "".join(payload_list)

    def flash_get_capacity(self):
        """
        Return the device flash capacity in bytes.

        Must be called *after* :meth:`flash_initial`!
        """
        # CMD_FLASH_GET_CAPACITY returns the size of flash in the
        # "length" field, but does not contain a payload.
        self._send_command(CMD_FLASH_GET_CAPACITY, wait_for_response = False)
        ack, _, capacity = self._read_response()

        if ack != ACK_SUCCESS:
            raise CommandResponseError(CMD_FLASH_GET_CAPACITY, ack, capacity)

        return capacity

    def flash_erase(self, start_address, size, erase_callback = None):
        """
        Erase the flash device, starting at ``start_address`` for ``size``
        bytes.

        If ``erase_callback`` is not ``None``, it is called for each erased block
        with arguments ``(block_index, block_size)``.

        **NOTE**: most flash devices will generally erase entire blocks. Block size
        is dependent on the flash device itself, but is usually many pages (e.g.,
        128 1 KB pages). If ``size`` does not match the block size boundary,
        more data will be erased to meet the boundary.
        """
        self._send_command(CMD_FLASH_ERASE,
                           address = start_address,
                           param1  = size,
                           param2  = 0,
                           wait_for_response = False)

        ack = ACK_FLASH_ERASE
        # The RAM kernel will send ACK_SUCCESS when the erase operation is complete.
        while ACK_FLASH_ERASE == ack:
            ack, i, block_size = self._read_response()

            # For each erased block, an ACK_FLASH_ERASE response is returned
            # from the RAM kernel specifying which block was erased, and
            # how big the block size is.
            if ACK_FLASH_ERASE == ack and erase_callback:
                erase_callback(i, block_size)

            if ack not in (ACK_FLASH_ERASE, ACK_SUCCESS):
                raise CommandResponseError(CMD_FLASH_ERASE, ack, block_size)

    def flash_program(self, start_address, data,
                      file_format = FLASH_FILE_FORMAT_NORMAL,
                      read_back_verify = False,
                      program_callback = None):
        """
        Program the flash device with ``data`` starting at ``start_address``.
        The maximum size of ``data`` is :const:`FLASH_PROGRAM_MAX_WRITE_SIZE`;
        break your write operation into multiple calls to this method.

        If ``read_back_verify`` is ``True``, the flash region to be programmed
        is read back for verification.

        If ``program_callback`` is specified, it is called for each page successfully
        written to flash or verified.  ``program_callback`` must take two parameters
        ``(write_length, total_written)``, where ``write_length`` is the length
        of the successful partial write operation and ``total_written`` is the total
        number of bytes written as of the callback.
        """
        if start_address < 0:
            raise ValueError("Invalid start address %r" % start_address)

        if len(data) == 0:
            raise ValueError("Data length must be non-zero.")
        if len(data) > FLASH_PROGRAM_MAX_WRITE_SIZE:
            raise ValueError("Data length is too large - max length is %d bytes." % FLASH_PROGRAM_MAX_WRITE_SIZE)

        if file_format not in (FLASH_FILE_FORMAT_NORMAL,
                               FLASH_FILE_FORMAT_NB0,
                               FLASH_FILE_FORMAT_OPS):
            raise ValueError("Invalid file format %r" % file_format)

        # FIXME: CMD_FLASH_PROGRAM_UB is not used in the supplied RAM kernel for NAND flash.
        # It seems to be for programming not at page boundaries? (UB = "un-boundary"
        # in the ATK source code).
        flash_command = CMD_FLASH_PROGRAM

        flags = file_format
        if read_back_verify:
            # flags |= FLASH_PROGRAM_PARAM1_VERIFY
            # TODO implement me!
            raise NotImplementedError("read_back_verify not yet implemented.")

        # The initial CMD_FLASH_PROGRAM tells the RAM kernel to prepare for len(data)
        # bytes to be sent.  It ACKs this initial request before the host sends
        # any data.
        self._send_command(flash_command,
                           address = start_address,
                           param1 = len(data),
                           param2 = flags,
                           wait_for_response = False)

        # We want to explicitly check for ACK_SUCCESS - we should not yet
        # read back ACK_FLASH_PARTLY
        ack, checksum, length = self._read_response()
        if ACK_SUCCESS != ack:
            raise CommandResponseError(flash_command, ack, length)

        # Send the entire data block at once. The underlying channel
        # breaks this into appropriate writeable chunks.
        self.channel.write(data)

        # Command responses send back the length of the partial write, but do not
        # include a payload.
        ack, checksum, length = self._read_response()
        if ack not in (ACK_SUCCESS, ACK_FLASH_PARTLY, ACK_FLASH_VERIFY):
            raise CommandResponseError(flash_command, ack, length)

        total_length = length
        while ACK_FLASH_PARTLY == ack:
            if program_callback:
                program_callback(length, total_length)

            ack, checksum, length = self._read_response()
            if ack not in (ACK_SUCCESS, ACK_FLASH_PARTLY, ACK_FLASH_VERIFY):
                raise CommandResponseError(flash_command, ack, length)

            total_length += length

        # TODO: read back verify messages

    def reset(self):
        """
        Reset the device CPU.
        """
        self._send_command(CMD_RESET, wait_for_response = False)
