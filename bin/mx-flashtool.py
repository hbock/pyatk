#!/usr/bin/env python
# Copyright (c) 2012-2013 Harry Bock <bock.harryw@gmail.com>
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
Portable Python command-line tool for bootstrapping i.MX processors.
"""

import os
import sys
import time
from optparse import OptionParser, OptionGroup

from pyatk.channel.uart import UARTChannel
from pyatk.channel.usbdev import USBChannel
from pyatk import boot
from pyatk import ramkernel
from pyatk import bspinfo

def writeln(line = ""):
    """
    Write a line to standard output.
    """
    sys.stdout.write(line + "\n")

def print_hex_dump(data, start_address, bytes_per_row = 16):
    """ Adjustable string hex dumper. """
    address = 0
    while address < len(data):
        sys.stdout.write("%08x : " % (start_address + address))

        row_data = bytearray(data[address:address + bytes_per_row])

        for column, byte in enumerate(row_data):
            sys.stdout.write("%02x " % byte)

        # If len(row_data) < bytes_per_row, pad with spaces to align
        # the printable view.
        sys.stdout.write(" " * (3 * (bytes_per_row - len(row_data))))
        sys.stdout.write("| ")

        for column, byte in enumerate(row_data):
            # Replace unprintable ASCII with '.'
            printable_byte = chr(byte) if (0x20 <= byte <= 0x7e) else "."
            sys.stdout.write(printable_byte)

        sys.stdout.write("\n")
        address += bytes_per_row

class ToolkitError(Exception):
    def __init__(self, msg):
        super(ToolkitError, self).__init__()
        self.msg = msg

    def __str__(self):
        return self.msg

class ToolkitApplication(object):
    def __init__(self, options):
        bsp_table_path = os.path.join(os.path.dirname(__file__), "bspinfo.conf")

        try:
            # TODO: look in home directory too!
            bsp_table = bspinfo.load_board_support_table([bsp_table_path])
        except IOError as e:
            raise ToolkitError("Unable to load BSP information table from %r: %s" % (bsp_table_path, e))

        self.bsp_info = bsp_table[options.bsp_name]

        # VID/PID specified explicitly
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

        # VID/PID inferred from BSP configuration
        else:
            vid = self.bsp_info.usb_vid
            pid = self.bsp_info.usb_pid


        if options.serialport:
            self.channel = UARTChannel(options.serialport)
        else:
            self.channel = USBChannel(idVendor = vid, idProduct = pid)
            self._usb = True

        self.options = options
        self.sbp = boot.SerialBootProtocol(self.channel)
        self.ramkernel = ramkernel.RAMKernelProtocol(self.channel)
        self.mem_init_data = []

    def channel_reinit(self):
        """ Close and re-open the ATK channel. """
        # This only applies to USB.  When the USB interface
        # is reset (either via loading an application
        # or resetting the CPU back into SBP mode), the interface
        # takes some time to reset and be recognized by the host
        # OS.
        # 
        # This takes longer when USB passthrough is used
        # for virtual machines, thus we attempt to re-connect
        # multiple times with a short timeout.
        #
        # It would be nice if we could wait for OS hotplug events,
        # but that's not possible with libusb (maybe libusbx?)
        # and it's not really worth the effort IMHO.
        if self._usb:
            self.channel.close()
            
            attempts = 0
            while attempts < 3:
                time.sleep(3)
                try:
                    self.channel.open()
                    break

                except IOError as err:
                    #writeln("Attempt {0} to re-open channel failed: {1}".format(attempts, err))
                    attempts += 1
            
            if attempts == 3:
                raise ToolkitError("unable to re-open USB channel! Is the device connected?")

    def run(self):
        writeln("Selected BSP %r." % self.options.bsp_name)
        writeln("Memory range: 0x%08X - 0x%08X" % (self.bsp_info.base_memory_address,
                                                 self.bsp_info.memory_bottom_address))

        self.load_mem_initializer()
        try:
            self.channel.open()
            status = self.sbp.get_status()
            writeln("Boot status: %s" % boot.get_status_string(status))
            
            self.memtest()
            self.mem_initialize()

            if self.options.ram_kernel_file is not None:
                self.run_ram_kernel()

            elif self.options.application_file is not None:
                self.run_application(self.options.application_file, self.options.application_address)

            if self.options.read_forever:
                writeln("Continuously reading from channel. Press Ctrl-C to exit.")
                writeln()

                while True:
                    data = self.channel.read(10)
                    if data != "":
                        sys.stdout.write(data)
                        sys.stdout.flush()

        except boot.CommandResponseError as exc:
            writeln("Command response error: %s" % exc)
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
        check = self.sbp.read_memory_single(0x78001000, boot.DATA_SIZE_WORD)
        if 0xBEEFDEAD != check:
            writeln("ERROR: SRAM write check failed: got 0x%08X" % check)

        self.sbp.write_memory(0x78001000, boot.DATA_SIZE_WORD, 0xBEEFCAFE)
        check = self.sbp.read_memory_single(0x78001000, boot.DATA_SIZE_WORD)
        if 0xBEEFCAFE != check:            
            writeln("ERROR: SRAM write check failed: got 0x%08X" % check)

    def mem_initialize(self):
        for initaddr, initval, initwidth in self.mem_init_data:
            writeln("init: write 0x%08X to 0x%08X (width %d)" % (initval, initaddr, initwidth))
            self.sbp.write_memory(initaddr, initwidth, initval)

    def run_ram_kernel(self):
        rk_file = self.options.ram_kernel_file
        rk_addr = self.options.ram_kernel_address
        if rk_addr == -1:
            rk_addr = self.bsp_info.ram_kernel_origin
            writeln("RAM kernel origin not specified; using BSP value 0x%08X" % rk_addr)
        else:
            writeln("Using user-specified RAM kernel origin: 0x%08X" % rk_addr)

        def load_cb(current, total):
            bar_len = 50
            bar_on = int(float(current) / total * bar_len)
            bar_off = bar_len - bar_on
            sys.stdout.write("[%s%s] %u/%u B\r" % ("="*bar_on, " "*bar_off, current, total))
            sys.stdout.flush()

        # Load and run the RAM kernel image.
        self.ramkernel.run_image_from_file(rk_file, self.bsp_info, load_cb)
        writeln()

        # Re-open channel
        self.channel_reinit()

        writeln("RAM kernel initialize flash.")
        self.ramkernel.flash_initial()
        writeln("RAM kernel getver():")
        imxtype, flashmodel = self.ramkernel.getver()
        writeln("Part number = 0x%04X (flash model = %r)" % (imxtype, flashmodel))
        writeln("RAM kernel flash capacity: %u Mb" % (self.ramkernel.flash_get_capacity() * 8 / 1024))

        try:
            if self.options.rkl_flash_test:
                self.ram_kernel_flash_test()
            elif self.options.rkl_flash_file:
                self.ram_kernel_flash_file(self.options.rkl_flash_file, self.options.rkl_flash_start_address)
            elif self.options.rkl_flash_dump:
                self.ram_kernel_dump(self.options.rkl_flash_start_address, self.options.rkl_flash_dump)

        except Exception as e:
            writeln("Unhandled exception: %s" % e)
            raise

        finally:
            writeln("\nEnd of RAM kernel test. Resetting CPU...")
            self.ramkernel.reset()
            self.channel_reinit()

            # Allow channel/bootstrap to settle
            time.sleep(2)

            writeln("SBP status after reset: " + boot.get_status_string(self.sbp.get_status()))

    def ram_kernel_dump(self, start_address, count, page_size = 2048):
        writeln("Dumping flash @ 0x%08x, count %d" % (start_address, count))
        writeln("Also dumping to dump.bin...")
        with open("dump.bin", "wb") as dump_fp:
            address = start_address
            while address < (start_address + count):
                data = self.ramkernel.flash_dump(address, page_size)
                print_hex_dump(data, address)
                dump_fp.write(data)

                address += page_size

    def ram_kernel_flash_file(self, path, start_address):
        ## FIXME this doesn't quite work yet... at least, I haven't gotten
        ## it to boot on any BSP yet.  Dumping flash to file (--flash-dump)
        ## and comparing against "path" show the files are binary identical.
        ## It must be something to do with either the image I'm testing,
        ## or not setting up the BBT.
        if start_address is None:
            raise ToolkitError("Flash start address not specified!")

        writeln("Programming %r to 0x%08x" % (path, start_address))
        block_size = 0x20000

        current_address = 0
        bar_len = 50

        class Progress(object):
            def __init__(self):
                self.program_current = 0
                self.verify_current  = 0
                self.current_address = 0
                self.start_time = time.time()

            def write_progress(self, current, length):
                ratio = float(self.program_current) / data_size
                percent = ratio * 100.0
                bar_on = int(ratio * bar_len)
                bar_off = bar_len - bar_on
                total_time = int(time.time() - self.start_time)

                sys.stdout.write("[%s%s] %u/%u B @ 0x%08X (%.2f%%) %02d:%02d\r" % \
                                 ("="*bar_on, " "*bar_off, current, data_size, current_address,
                                     percent, total_time / 60, total_time % 60))
                sys.stdout.flush()

            def program_cb(self, block, write_length):
                sys.stdout.write("Program ")
                self.write_progress(self.program_current, write_length)
                self.program_current += write_length

            def verify_cb(self, block, verify_length):
                sys.stdout.write("Verify  ")
                self.write_progress(self.verify_current, verify_length)
                self.verify_current += verify_length

        data_size = os.stat(path).st_size
        num_blocks = data_size / block_size
        # flash_program will only write starting at the block boundary.
        # The RAM kernel will pretend it is writing to the specified address,
        # but it always erases and then writes starting from block page 0.
        # Thus, we pad the data if the start address starts after the first
        # byte of the block.
        block_start = (start_address & ~(block_size-1))
        if block_start < start_address:
            initial_pad = "\x00" * (start_address - block_start)
            writeln("Flash program start address does not fall on block boundary.")
            writeln("Writing {0} pad bytes at start of block.".format(len(initial_pad)))
        else:
            initial_pad = ""

        with open(path, "rb") as file_fp:
            read_size = block_size
            # Start writing at block start address
            current_address = block_start
            # Pad the first read from the file, adjusted for the remaining size of the
            # block.
            chunk = initial_pad + file_fp.read(read_size - len(initial_pad))

            prog = Progress()
            while current_address < (start_address + data_size):
                self.ramkernel.flash_program(current_address, chunk,
                                             read_back_verify = True,
                                             program_callback = prog.program_cb,
                                             verify_callback  = prog.verify_cb)
                current_address += len(chunk)
                chunk = file_fp.read(read_size)

    def ram_kernel_flash_test(self):
        writeln("Running RKL flash test.")
        writeln("read flash first page:")
        start_address = 0x0000
        flash_page = self.ramkernel.flash_dump(start_address, 1024)
        print_hex_dump(flash_page, start_address)

        def erase_cb(block_index, block_size):
            writeln("Erased block %d (size %d bytes)." % (block_index, block_size))

        size = 4096 * 4
        writeln("Erasing first %d bytes." % size)
        self.ramkernel.flash_erase(start_address, size, erase_callback = erase_cb)
        writeln("Dump after erase...")
        flash_page = self.ramkernel.flash_dump(start_address, size)
        print_hex_dump(flash_page, start_address)

        writeln("Test flashing DEADBEEF to first page...")
        self.ramkernel.flash_program(start_address, "\xDE\xAD\xBE\xEF" * (size/8),
                                     read_back_verify = True,
                                     program_callback = program_cb,
                                     verify_callback  = verify_cb)

        writeln("Dump after program...")
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
            writeln("Writing application %r to 0x%08X" % (filename, load_address))
            self.sbp.write_file(boot.FILE_TYPE_APPLICATION,
                                load_address, image_size, appl_fd, progress_callback = progcb)
            self.sbp.complete_boot()

            writeln("\nApplication write/execute OK!")

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
    parser = OptionParser(
        "i.MX Serial Bootloader / Flash Toolkit\n\n"

        "Flashing a program via a RAM kernel to the start of flash:\n"
        "  %prog -b PLAT_BSP -i init.txt -k ramkernel.bin --flash-file BOARD.ROM --flash-address 0\n\n"

        "Executing an application (u-boot.bin) compiled to start at 0x82000000:\n"
        "  %prog -b PLAT_BSP -i init.txt -f u-boot.bin -a 0x82000000\n\n"

        "Dumping 2 kB of flash memory starting at address 0x00000000:\n"
        "  %prog -b PLAT_BSP -i init.txt -k ramkernel.bin --flash-dump 2048 --flash-address 0\n\n"

        "Manually specify USB VID/PID (PID is optional):\n"
        "  %prog -b PLAT_BSP -uVID[:PID] ...\n"
        "Or serial port (COMx on Windows, /dev/ttyusbX on Linux, etc.):\n"
        "  %prog -b PLAT_BSP -s COM1 ..."
    )
    parser.add_option("--bsp", "-b", action = "store",
                      dest = "bsp_name", metavar = "PLATFORM",
                      help = "Platform BSP name (e.g., mx25)")
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
                       default = -1,
                       help = ("RAM kernel helper application origin address "
                               "(default to BSP definition)."))
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
                        help = "Use serial port DEVICE instead of USB.")
    comgroup.add_option("--usb", "-u", action = "store",
                        dest = "usb_vid_pid", metavar = "VID[:PID]",
                        help = "Override USB vendor ID/product ID in BSP data.")
    comgroup.add_option("--read-forever", "-r", action = "store_true",
                        dest = "read_forever", default = False,
                        help  = ("Read continuously from communication channel after "
                                 "loading application, displaying to terminal."))

    parser.add_option_group(rkgroup)
    parser.add_option_group(comgroup)
    
    options, args = parser.parse_args()

    if not options.bsp_name:
        parser.error("Please select a BSP name.")
    if options.serialport and options.usb_vid_pid:
        parser.error("Cannot select both a serial port and a USB device!")

    if options.application_file and not options.application_address:
        parser.error("Application file specified without address.")

    atkprog = ToolkitApplication(options)
    try:
        atkprog.run()

    except KeyboardInterrupt:
        writeln("User exit.")
        sys.exit(1)

    except IOError as exc:
        writeln("I/O error: %s" % exc)

    except ToolkitError as exc:
        parser.error(str(exc))

if __name__ == "__main__":
    main()