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
from pyatk.channel.usbdev import USBChannel
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
    def __init__(self, options):

        if options.usb_vid_pid:
            try:
                if ":" in options.usb_vid_pid:
                    vid_str, pid_str = options.usb_vid_pid.partition(":")
                    vid = int(vid_str, 0)
                    pid = int(pid_str, 0)
                else:
                    vid = int(options.usb_vid_pid, 0)
                    pid = None

            except ValueError:
                raise ToolkitError("Could not convert USB VID/PID %r to integer." % options.usb_vid_pid)

            else:
                self.channel = USBChannel(idVendor = vid, idProduct = pid)

        elif options.serialport:
            self.channel = UARTChannel(options.serialport)

        self.options = options

        self.sbp = boot.SerialBootProtocol(self.channel)
        self.ramkernel = ramkernel.RAMKernelProtocol(self.channel)
        self.mem_init_data = []

    def run(self):
        self.load_mem_initializer()
        try:
            self.channel.open()
            status = self.sbp.get_status()
            print "Boot status:", boot.get_status_string(status)
            
            self.memtest()
            self.mem_initialize()

            if self.options.ram_kernel_file is not None:
                self.run_ram_kernel()

            elif self.options.application_file is not None:
                self.run_application(self.options.application_file, self.options.application_address)

            if self.options.read_forever:
                print "Continuously reading from channel. Press Ctrl-C to exit."
                print
                while True:
                    data = self.channel.read(10)
                    if data != "":
                        sys.stdout.write(data)
                        sys.stdout.flush()

        except boot.CommandResponseError, exc:
            print "Command response error: %s" % exc
            sys.exit(1)

        finally:
            if self.channel:
                self.channel.close()

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

        print "waiting after ram kernel start... (ctrl+C to shortcut)"
        try:
            time.sleep(3)
        except KeyboardInterrupt:
            pass

        #sys.exit(1)
        #self.channel.reconnect()
        self.channel.open()

        print "ram kernel initialize flash"
        self.ramkernel.flash_initial()
        print "ram kernel getver:"
        imxtype, flashmodel = self.ramkernel.getver()
        print "Part number = 0x%04X (flash model = %r)" % (imxtype, flashmodel)
        print "RAM kernel flash capacity: %u Mb" % (self.ramkernel.flash_get_capacity() * 8 / 1024)

        try:
            if self.options.rkl_flash_test:
                self.ram_kernel_flash_test()
            elif self.options.rkl_flash_file:
                self.ram_kernel_flash_file(self.options.rkl_flash_file, self.options.rkl_flash_start_address)
            elif self.options.rkl_flash_dump:
                self.ram_kernel_dump(self.options.rkl_flash_start_address, self.options.rkl_flash_dump)

        finally:
            print("End of RAM kernel test. Resetting CPU.")
            self.ramkernel.reset()
            time.sleep(1)
            print("SBP status after reset: " + boot.get_status_string(self.sbp.get_status()))

    def ram_kernel_dump(self, start_address, count, page_size = 2048):
        print("Dumping flash @ 0x%08x, count %d" % (start_address, count))
        print("Also dumping to dump.bin...")
        with open("dump.bin", "wb") as dump_fp:
            for address in xrange(start_address, start_address + count, page_size):
                data = self.ramkernel.flash_dump(address, page_size)
                print_hex_dump(data, address)
                dump_fp.write(data)

    def ram_kernel_flash_file(self, path, start_address):
        ## FIXME this doesn't quite work yet... at least, I haven't gotten
        ## it to boot on any BSP yet.  Dumping flash to file (--flash-dump)
        ## and comparing against "path" show the files are binary identical.
        ## It must be something to do with either the image I'm testing,
        ## or not setting up the BBT.
        if start_address is None:
            raise ToolkitError("Flash start address not specified!")

        print("Programming %r to 0x%08x" % (path, start_address))
        block_size = 0x20000

        data_size = os.stat(path).st_size
        def prog_cb(block, length):
            print("Programmed block %d, length %d" % (block, length))
        def erase_cb(block, length):
            print("Erased block %d, length %d" % (block, length))
        def verify_cb(block, length):
            print("Verified block %d, length %d" % (block, length))

        print("Erasing address %d, %d bytes" % (start_address, data_size))
        self.ramkernel.flash_erase(start_address, data_size, erase_callback=erase_cb)

        with open(path, "rb") as file_fp:
            read_size = block_size
            current_address = start_address
            chunk = file_fp.read(read_size)

            while current_address < (start_address + data_size):
                print("Programming %d bytes @ 0x%08x." % (len(chunk), current_address))
                self.ramkernel.flash_program(current_address, chunk,
                                             read_back_verify = True,
                                             program_callback = prog_cb,
                                             verify_callback  = verify_cb)
                current_address += len(chunk)
                chunk = file_fp.read(read_size)

    def ram_kernel_flash_test(self):
        print("Running RKL flash test.")
        print("read flash first page:")
        start_address = 0x0000
        flash_page = self.ramkernel.flash_dump(start_address, 1024)
        print_hex_dump(flash_page, start_address)

        def erase_cb(block_index, block_size):
            print("Erased block %d (size %d bytes)." % (block_index, block_size))

        size = 4096 * 4
        print("Erasing first %d bytes." % size)
        self.ramkernel.flash_erase(start_address, size, erase_callback = erase_cb)
        print("Dump after erase...")
        flash_page = self.ramkernel.flash_dump(start_address, size)
        print_hex_dump(flash_page, start_address)

        def program_cb(block, write_length):
            print("Programmed block %d, length %d (%d total)" % (block, write_length))
        def verify_cb(block, verify_length):
            print("Verified block %d, length %d" % (block, verify_length))

        print("Test flashing DEADBEEF to first page...")
        self.ramkernel.flash_program(start_address, "\xDE\xAD\xBE\xEF" * (size/8),
                                     read_back_verify = True,
                                     program_callback = program_cb,
                                     verify_callback  = verify_cb)

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
    rkgroup.add_option("--flash-dump", "-d", action = "store", type = "int",
                       dest = "rkl_flash_dump", metavar = "COUNT",
                       help = "Dump COUNT bytes of flash starting at --flash-address.")
    rkgroup.add_option("--flash-file", action = "store",
                       dest = "rkl_flash_file",
                       metavar = "FILENAME",
                       help = "Program this file to device flash memory.")
    rkgroup.add_option("--flash-address", action = "store", type = "int",
                       dest = "rkl_flash_start_address",
                       metavar = "ADDRESS",
                       help = "Starting writing to device flash memory at ADDRESS.")

    comgroup = OptionGroup(parser, "Communications")
    comgroup.add_option("--serialport", "-s", action = "store",
                        dest = "serialport", metavar = "DEVICE",
                        help = "Serial port device name.")
    comgroup.add_option("--usb", "-u", action = "store",
                        dest = "usb_vid_pid", metavar = "VID[:PID]",
                        help = "USB vendor ID/product ID")
    comgroup.add_option("--read-forever", "-r", action = "store_true",
                        dest = "read_forever", default = False,
                        help  = ("Read continuously from communication channel after "
                                 "loading application, displaying to terminal."))

    parser.add_option_group(rkgroup)
    parser.add_option_group(comgroup)
    
    options, args = parser.parse_args()

    if not (options.serialport or options.usb_vid_pid):
        parser.error("Please select a serial port/USB device.")
    if options.serialport and options.usb_vid_pid:
        parser.error("Cannot select both a serial port and a USB device!")

    if options.application_file and not options.application_address:
        parser.error("Application file specified without address.")

    atkprog = ToolkitApplication(options)
    try:
        atkprog.run()

    except KeyboardInterrupt:
        print "User exit."
        sys.exit(1)

    except IOError, exc:
        print "I/O error: %s" % exc

    except ToolkitError, exc:
        parser.error(str(exc))

if __name__ == "__main__":
    main()
