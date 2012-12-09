#!/usr/bin/env python
# Copyright (c) 2012 Harry Bock <bock.harryw@gmail.com>
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
Portable Python ATK implementation
"""

import re
import os
import sys
import time
from optparse import OptionParser, OptionGroup

from pyatk.channel.uart import UARTChannel
from pyatk import boot
from pyatk import ramkernel

DEFAULT_RAM_KERNEL_ADDRESS = 0x80004000

def print_hex_dump(data, start_address, bytes_per_row = 16):
    """ Adjustable string hex dumper. """
    for address in xrange(0, len(data), bytes_per_row):
        sys.stdout.write("%08x : " % (start_address + address))

        row_data = data[address:address + bytes_per_row]

        for column, byte in enumerate(row_data):
            sys.stdout.write("%02x " % ord(byte))

        # If len(row_data) < bytes_per_row, pad with spaces to align
        # the printable view.
        sys.stdout.write(" " * (3 * (bytes_per_row - len(row_data))))
        sys.stdout.write("| ")

        # Replace unprintable ASCII with '.'
        printable_row_data = re.sub("[^\x20-\x7e]", ".", row_data)
        for column, byte in enumerate(printable_row_data):
            sys.stdout.write("%c" % byte)

        sys.stdout.write("\n")

class ToolkitError(Exception):
    def __init__(self, msg):
        super(ToolkitError, self).__init__()
        self.msg = msg

    def __str__(self):
        return self.msg

class ToolkitApplication(object):
    def __init__(self, chan, options):
        self.channel = chan
        self.options = options

        self.sbp = boot.SerialBootProtocol(chan)
        self.ramkernel = ramkernel.RAMKernelProtocol(chan)
        self.mem_init_data = []

    def run(self):
        self.load_mem_initializer()
        try:
            status = self.sbp.get_status()
            print "Boot status:", boot.get_status_string(status)
            
            self.memtest()
            self.mem_initialize()

            if self.options.ram_kernel_file is not None:
                self.run_ram_kernel()

            elif self.options.application_file is not None:
                self.run_application(self.options.application_file, self.options.application_address)

        except boot.CommandResponseError, exc:
            print "Command response error: %s" % exc
            sys.exit(1)

    def load_mem_initializer(self):
        if self.options.init_file:
            self.mem_init_data = read_initialization_file(self.options.init_file)
        elif self.options.ram_kernel_file:
            raise ToolkitError("RAM kernel selected, but initialization file missing.")
        
    def load_application(self, application_file, application_address):
        pass

    def memtest(self):
        # Initial memory test
        self.sbp.write_memory(0x78001000, boot.DATA_SIZE_WORD, 0xBEEFDEAD)
        check = self.sbp.read_memory(0x78001000, boot.DATA_SIZE_WORD)
        if 0xBEEFDEAD != check:
            print "ERROR: SRAM write check failed: got 0x%08X" % check        

        self.sbp.write_memory(0x78001000, boot.DATA_SIZE_WORD, 0xBEEFCAFE)
        check = self.sbp.read_memory(0x78001000, boot.DATA_SIZE_WORD)
        if 0xBEEFCAFE != check:            
            print "ERROR: SRAM write check failed: got 0x%08X" % check

    def mem_initialize(self):
        for initaddr, initval, initwidth in self.mem_init_data:
            print "init: write 0x%08X to 0x%08X (width %d)" % (initval, initaddr, initwidth)
            self.sbp.write_memory(initaddr, initwidth, initval)

    def run_ram_kernel(self):
        rk_file = self.options.ram_kernel_file
        rk_addr = self.options.ram_kernel_address

        print "loading ram kernel %r" % rk_file 
        self.run_application(rk_file, rk_addr)

        print "waiting after ram kernel start..."
        time.sleep(1)

        print "ram kernel initialize flash"
        self.ramkernel.flash_initial()
        print "ram kernel getver:"
        imxtype, flashmodel = self.ramkernel.getver()
        print "Part number = 0x%04X (flash model = %r)" % (imxtype, flashmodel)
        print "RAM kernel flash capacity: %u Mb" % (self.ramkernel.flash_get_capacity() * 8 / 1024)

        if self.options.rkl_flash_test:
            self.ram_kernel_flash_test()

        print("End of RAM kernel test. Resetting CPU.")
        self.ramkernel.reset()
        time.sleep(1)
        print("SBP status after reset: " + boot.get_status_string(self.sbp.get_status()))

    def ram_kernel_flash_test(self):
        print("Running RKL flash test.")
        print("read flash first page:")
        start_address = 0x0000
        flash_page = self.ramkernel.flash_dump(start_address, 1024)
        print_hex_dump(flash_page, start_address)

        def erase_cb(block_index, block_size):
            print("Erased block %d (size %d bytes)." % (block_index, block_size))

        print("Erasing first two pages.")
        size = 2048
        self.ramkernel.flash_erase(start_address, size, erase_callback = erase_cb)
        print("Dump after erase...")
        flash_page = self.ramkernel.flash_dump(start_address, size)
        print_hex_dump(flash_page, start_address)

        def program_cb(length, total_bytes_written):
            print("Programmed %d bytes (%d total)" % (length, total_bytes_written))

        print("Test flashing DEADBEEF to first page...")
        self.ramkernel.flash_program(start_address, "\xDE\xAD\xBE\xEF" * (size/8),
                                     program_callback = program_cb)
        print("Dump after program...")
        flash_page = self.ramkernel.flash_dump(start_address, size)
        print_hex_dump(flash_page, start_address)

    def run_application(self, filename, load_address):
        appl_stat = os.stat(filename)
        image_size = appl_stat.st_size
        def progcb(current, total):
            bar_len = 50
            bar_on = int(float(current) / total * bar_len)
            bar_off = bar_len - bar_on
            sys.stdout.write("[%s%s] %u/%u B\r" % ("="*bar_on, " "*bar_off, current, total))
            sys.stdout.flush()

        with open(filename, "rb") as appl_fd:
            print "Writing application %r to 0x%08X" % (filename, load_address)
            self.sbp.write_file(boot.FILE_TYPE_APPLICATION,
                                load_address, image_size, appl_fd, progress_callback = progcb)
            self.sbp.complete_boot()
            print
            print "Application write/execute OK!"

        if self.options.read_forever:
            print "Continuously reading from channel. Press Ctrl-C to exit."
            print
            start_time = time.time()
            while True:
                data = self.channel.read(10)
                if data != "":
                    sys.stdout.write(data)
                    sys.stdout.flush()

def read_initialization_file(filename):
    with open(filename, "r") as initfp:
        initialization_data = []
        for line in initfp:
            line = line.strip()
            if line == "" or line.startswith("#"):
                continue

            data = line.split(" ")
            memaddr  = int(data[0], 0)
            memval   = int(data[1], 0)
            memwidth = int(data[2], 0)

            initialization_data.append((memaddr, memval, memwidth))

        return initialization_data

def main():
    parser = OptionParser("%prog -s DEVICE [-k ramkernel] [-i init.txt] [application]")
    parser.add_option("--initialization-file", "-i", action = "store",
                      dest = "init_file", metavar = "FILE",
                      help = "Memory initialization file.")
    parser.add_option("--appl-file", "-f", action = "store",
                      dest = "application_file", metavar = "FILE",
                      help = "Application binary.")
    parser.add_option("--appl-address", "-a", action = "store",
                      dest = "application_address", type = "int", metavar = "ADDRESS",
                      help = ("Application start address."))

    rkgroup = OptionGroup(parser, "RAM Kernel Options")
    rkgroup.add_option("--ram-kernel", "-k", action = "store",
                       dest = "ram_kernel_file", metavar = "FILE",
                       help = "RAM kernel helper application binary.")
    rkgroup.add_option("--ram-kernel-address", action = "store",
                       dest = "ram_kernel_address", type = "int", metavar = "ADDRESS",
                       default = DEFAULT_RAM_KERNEL_ADDRESS,
                       help = ("RAM kernel helper application base address "
                               "(default DRAM 0x%08X)." % DEFAULT_RAM_KERNEL_ADDRESS))
    rkgroup.add_option("--flash-test", "-t", action = "store_true",
                       dest = "rkl_flash_test",
                       help = "Test the flash part using the RAM kernel.",
                       default = False)

    comgroup = OptionGroup(parser, "Communications")
    comgroup.add_option("--serialport", "-s", action = "store",
                        dest = "serialport", metavar = "DEVICE",
                        help = "Serial port device name.")
    comgroup.add_option("--read-forever", "-r", action = "store_true",
                        dest = "read_forever", default = False,
                        help  = ("Read continuously from communication channel after "
                                 "loading application, displaying to terminal."))

    parser.add_option_group(rkgroup)
    parser.add_option_group(comgroup)
    
    options, args = parser.parse_args()

    if not options.serialport:
        parser.error("Please select a serial port.")

    if options.application_file and not options.application_address:
        parser.error("Application file specified without address.")

    serial_channel = UARTChannel(options.serialport)
    serial_channel.open()
    atkprog = ToolkitApplication(serial_channel, options)
    try:
        atkprog.run()

    except KeyboardInterrupt:
        print "User exit."
        sys.exit(1)

    except IOError, exc:
        print "I/O error: %s" % exc

    except ToolkitError, exc:
        parser.error(str(exc))

    finally:
        serial_channel.close()

if __name__ == "__main__":
    main()
