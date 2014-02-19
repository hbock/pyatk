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
import traceback
from optparse import OptionParser, OptionGroup

from pyatk.channel.uart import UARTChannel
from pyatk.channel.usbdev import USBChannel
from pyatk import boot
from pyatk import ramkernel
from pyatk import bspinfo
from pyatk import __version__ as pyatk_version

MX_FLASHTOOL_VERSION = "0.0.3"

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
    def __init__(self):
        self.bsp_info = None
        self.channel = None
        self.sbp = None

    def bsp_initialize(self, options, require_bsp = True):
        bsp_table = get_bsp_table(options)
        if require_bsp and not options.bsp_name:
            raise ToolkitError("Please select a BSP name, or run command 'listbsp' to see "
                               "available BSPs.")


        try:
            self.bsp_info = bsp_table[options.bsp_name]

        except KeyError:
            if require_bsp:
                raise ToolkitError("Unable to find requested BSP name %r!" % (options.bsp_name,))

        return bsp_table

    def channel_init(self, options):
        if options.serialport and options.usb_vid_pid:
            raise ToolkitError("Cannot select both a serial port and a USB device!")

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

        self.sbp = boot.SerialBootProtocol(self.channel)

        writeln(" [*] Opening bootstrap communications channel...")
        try:
            self.channel.open()
        except IOError as err:
            writeln(" <!> Failed to open communications channel!")
            writeln(" <!> %s" % (err,))
            sys.exit(1)

        status = self.sbp.get_status()
        writeln(" [*] Initial boot status: %s" % boot.get_status_string(status))

        self.mem_initialize(options)
        try:
            self.mem_test()
        except IOError:
            writeln(" [!] Memory test failed. Perhaps your memory init file ")
            writeln("     is missing or invalid for your target.")
            raise

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
            writeln(" [*] Re-initialize USB channel.")
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
                raise IOError("unable to re-open USB channel! Is the device connected?")

    def get_base_parser(self, command_specific_help = ""):
        parser = OptionParser(
            "i.MX Flash Toolkit version " + MX_FLASHTOOL_VERSION +
            " (API version " + pyatk_version +
            ")\n\n" + command_specific_help,
            version=MX_FLASHTOOL_VERSION
        )
        group = OptionGroup(parser, "Board Support Package (BSP) Configuration")
        group.add_option("--bsp", "-b", action = "store",
                         dest = "bsp_name", metavar = "PLATFORM",
                         help = "Platform BSP name (e.g., mx25)")
        group.add_option("--bsp-config", "-c", action = "store",
                         dest = "bsp_config_file", metavar = "CONFIGFILE",
                         default = os.path.join(os.getcwd(), "bspinfo.conf"),
                         help = "Optional BSP config file (defaults to $(PWD)/bspinfo.conf)")
        parser.add_option_group(group)

        parser.add_option("--initialization-file", "-i", action = "store",
                          dest = "init_file", metavar = "FILE",
                          help = "Memory initialization file.")

        comgroup = OptionGroup(parser, "Communications")
        comgroup.add_option("--serialport", "-s", action = "store",
                            dest = "serialport", metavar = "DEVICE",
                            help = "Use serial port DEVICE instead of USB.")
        comgroup.add_option("--usb", "-u", action = "store",
                            dest = "usb_vid_pid", metavar = "VID[:PID]",
                            help = "Override USB vendor ID/product ID in BSP data.")

        parser.add_option_group(comgroup)

        return parser

    def run_list_bsp(self, args):
        parser = self.get_base_parser()
        options, args = parser.parse_args(args)
        bsp_table = self.bsp_initialize(options, require_bsp=False)

        writeln("Listing BSP data:")
        writeln("-----------------")
        for bsp_name in bsp_table:
            bsp_data = bsp_table[bsp_name]
            writeln(" [*] %-10s -- %s" % (bsp_name, bsp_data.description))

    def run_flash(self, args):
        #
        # "Manually specify USB VID/PID (PID is optional):\n"
        # "  %prog -b PLAT_BSP -uVID[:PID] ...\n"
        # "Or serial port (COMx on Windows, /dev/ttyusbX on Linux, etc.):\n"
        # "  %prog -b PLAT_BSP -s COM1 ...",

        parser = self.get_base_parser(
            "Flashing a program via a RAM kernel to the start of flash (0x0):\n"
            "  %prog flash program -b PLAT_BSP BOARD.ROM 0x0\n\n"
            "Dumping 2 kB of flash memory starting at address 0x00000000:\n"
            "  %prog flash dump -b PLAT_BSP 2048 0x0"
        )

        rkgroup = OptionGroup(parser, "Flash Command Options")
        rkgroup.add_option("--ram-kernel", "-k", action = "store",
                           dest = "ram_kernel_file", metavar = "FILE",
                           help = "RAM kernel helper application binary.")
        rkgroup.add_option("--ram-kernel-address", "-a", action = "store",
                           dest = "ram_kernel_address", type = "int", metavar = "ADDRESS",
                           default = -1,
                           help = ("RAM kernel helper application origin address "
                                   "(default to BSP definition)."))
        rkgroup.add_option("--dump-file", "-f", action = "store",
                           dest = "flash_dump_file", metavar = "FILE",
                           default = "dump.bin",
                           help = ("File to write to for 'flash dump' command. Default "
                                   "is 'dump.bin'"))
        rkgroup.add_option("--no-print", "-n", action = "store_false",
                           dest = "print_flash_dump", default = True,
                           help = "Set this flag to disable dumping flash to the console.")
        rkgroup.add_option("--bbt", action = "store_true",
                           dest = "set_bbt_flag", default = False,
                           help = ("Set this flag to enable bad block table (BBT) "
                                   "handling in the RAM kernel."))

        parser.add_option_group(rkgroup)

        options, args = parser.parse_args(args)
        self.bsp_initialize(options)
        self.channel_init(options)
        self.run_ram_kernel(options, args)

    def run_run(self, args):
        parser = self.get_base_parser(
            "Execute an application (u-boot.bin) compiled to start at 0x82000000:\n"
            "  %prog run -b PLAT_BSP u-boot.bin 0x82000000"
        )
        options, args = parser.parse_args(args)

        application_file = args[0]
        try:
            load_address = int(args[1], 0)

        except ValueError:
            raise ToolkitError("Invalid flash address %r!" % (args[1],))

        self.bsp_initialize(options)
        self.channel_init(options)
        self.run_application(application_file, load_address)

    def run(self, command, args):
        command_map = {
            "flash": self.run_flash,
            "listbsp": self.run_list_bsp,
            "run": self.run_run,
        }
        if command.lower() not in command_map:
            raise ToolkitError("Invalid command %r!" % (command,))

        # Strip off the initial command
        command_map[command](args)

        # except boot.CommandResponseError as exc:
        #     writeln("Command response error: %s" % exc)
        #     sys.exit(1)
        #
        # finally:
        #     if self.channel:
        #         self.channel.close()

    def load_application(self, application_file, application_address):
        pass

    def mem_test(self):
        writeln(" [i] Memory test...")
        # Initial memory test
        memory_test_addr = self.bsp_info.base_memory_address
        self.sbp.write_memory(memory_test_addr, boot.DATA_SIZE_WORD, 0xBEEFDEAD)
        check = self.sbp.read_memory_single(memory_test_addr, boot.DATA_SIZE_WORD)
        if 0xBEEFDEAD != check:
            writeln("ERROR: Memory write check failed: got 0x%08X" % check)

        memory_test_addr += 0x1000
        self.sbp.write_memory(memory_test_addr, boot.DATA_SIZE_WORD, 0xBEEFCAFE)
        check = self.sbp.read_memory_single(memory_test_addr, boot.DATA_SIZE_WORD)
        if 0xBEEFCAFE != check:            
            writeln("ERROR: SRAM write check failed: got 0x%08X" % check)

    def mem_initialize(self, options):
        init_file = None
        # If the -i option is specified, use that over the BSP file.
        if options.init_file:
            init_file = options.init_file

        # If the -i option is NOT specified, see if there is a BSP file.
        elif self.bsp_info.memory_init_file:
            init_file = self.bsp_info.memory_init_file

        if init_file is not None:
            mem_init_data = read_initialization_file(init_file)
            writeln(" [*] Initializing processor memory...")
            for initaddr, initval, initwidth in mem_init_data:
                if boot.DATA_SIZE_WORD == initwidth:
                    writeln("  [>] Write 0x%08X to 0x%08X" % (initval, initaddr))
                if boot.DATA_SIZE_HALFWORD == initwidth:
                    writeln("  [>] Write 0x%04X to 0x%08X" % (initval, initaddr))
                if boot.DATA_SIZE_BYTE == initwidth:
                    writeln("  [>] Write 0x%02X to 0x%08X" % (initval, initaddr))
                self.sbp.write_memory(initaddr, initwidth, initval)
        else:
            writeln(" [W] No memory initialization file specified.")
            writeln(" [W] Device communication may not work at all.")

    def run_ram_kernel(self, options, args):
        kernel = ramkernel.RAMKernelProtocol(self.channel)

        if options.ram_kernel_file:
            writeln(" [-] Using RAM kernel binary from command line.")
            rk_file = options.ram_kernel_file

        elif self.bsp_info.ram_kernel_file:
            rk_file = self.bsp_info.ram_kernel_file
            writeln(" [-] Using RAM kernel binary from BSP configuration.")
            writeln(" [-]   %s" % (rk_file,))

        else:
            raise ToolkitError("No RAM kernel file specified.")

        rk_addr = options.ram_kernel_address

        if rk_addr == -1:
            rk_addr = self.bsp_info.ram_kernel_origin
            writeln(" [-]   Kernel origin not specified; using BSP value 0x%08X" % rk_addr)
        else:
            writeln(" [-]   Using user-specified kernel origin: 0x%08X" % rk_addr)


        try:
            flash_command = args[0]
            if "erase" == flash_command:
                flash_run_method = self.ram_kernel_flash_erase
            elif "program" == flash_command:
                flash_run_method = self.ram_kernel_flash_file
            elif "dump" == flash_command:
                flash_run_method = self.ram_kernel_flash_dump
            else:
                raise ToolkitError("Unknown 'flash' subcommand %r!" % (flash_command,))

        except IndexError:
            raise ToolkitError("Missing subcommand for 'flash' command!")

        def load_cb(current, total):
            current //= 1024
            total //= 1024
            bar_len = 25
            bar_on = int(float(current) / total * bar_len)
            bar_off = bar_len - bar_on
            sys.stdout.write("     [%s%s] %u / %u kB\r" % ("="*bar_on,
                                                           " "*bar_off,
                                                           current,
                                                           total))
            sys.stdout.flush()

        # Load and run the RAM kernel image.
        writeln(" [*] Loading and executing RAM kernel...")
        kernel.run_image_from_file(rk_file, self.bsp_info, load_cb)
        writeln()

        # Re-open channel
        self.channel_reinit()

        try:
            enable_disable_str = ("enable" if options.set_bbt_flag else "disable")
            writeln(" [*] Set flash BBT handling: %s" % (enable_disable_str,))
            kernel.flash_set_bbt(options.set_bbt_flag)

            writeln(" [*] Initializing flash part...")
            kernel.flash_initial()
            writeln(" [?] Querying RAM kernel for version information:")
            imxtype, flashmodel = kernel.getver()
            writeln("    [>] Part number:    %u" % (imxtype,))
            writeln("    [>] Flash model:    %r" % (flashmodel,))

            flash_capacity_mbits = kernel.flash_get_capacity() * 8 / 1024
            writeln("    [>] Flash capacity: %u Mb" % (flash_capacity_mbits,))

            flash_run_method(kernel, options, args[1:])

        except ramkernel.CommandResponseError as err:
            writeln(" <!> RAM kernel error: %s" % (err,))

        except Exception as err:
            tb = sys.exc_info()[2]
            writeln(" <!> Unhandled error: %s" % (err,))
            writeln(" <!> Traceback: %s" % ("\n".join(traceback.format_tb(tb)),))

        finally:
            writeln(" [*] Resetting CPU...")
            # Sometimes we need to let the RAM kernel "settle" after
            # flash commands before issuing the RKL reset command.
            time.sleep(1)
            kernel.reset()
            self.channel_reinit()

            # Allow channel/bootstrap to settle
            time.sleep(2)

            writeln(" [*] Bootstrap status after reset: %s" % (
                boot.get_status_string(self.sbp.get_status()),
            ))

    def ram_kernel_flash_dump(self, kernel, options, args):
        count = int(args[0], 0)
        page_size = 2048

        if len(args) > 1:
            address = args[1]
            try:
                start_address = int(address, 0)
            except ValueError:
                raise ToolkitError("Invalid flash address %r!" % (address,))
        else:
            writeln(" [*] Start address not specified; starting at block 0.")
            start_address = 0

        writeln(" [*] Dumping flash @ 0x%08x, count %d" % (start_address, count))
        writeln(" [*] Also dumping to %s..." % (options.flash_dump_file,))
        with open(options.flash_dump_file, "wb") as dump_fp:
            address = start_address
            while address < (start_address + count):
                data = kernel.flash_dump(address, page_size)
                # Only dump to console if requested
                if options.print_flash_dump:
                    print_hex_dump(data, address)
                # Write out data
                dump_fp.write(data)
                address += page_size

    def ram_kernel_flash_file(self, kernel, options, args):
        path = args[0]

        if len(args) > 1:
            address = args[1]
            try:
                start_address = int(address, 0)
            except ValueError:
                raise ToolkitError("Invalid flash address %r!" % (address,))
        else:
            writeln(" [*] Start address not specified; starting at block 0.")
            start_address = 0

        writeln(" [*] Programming %r to 0x%08x" % (path, start_address))
        block_size = 0x20000

        current_address = 0
        bar_len = 35

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

                sys.stdout.write("[%s%s] 0x%08X (%5.2f%%) %02d:%02d\r" % \
                                 ("="*bar_on, " "*bar_off,
                                  current_address, percent, total_time / 60, total_time % 60))

                sys.stdout.flush()

            def program_cb(self, block, write_length):
                sys.stdout.write("     Program ")
                self.write_progress(self.program_current, write_length)
                self.program_current += write_length

            def verify_cb(self, block, verify_length):
                sys.stdout.write("     Verify  ")
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
            initial_pad = b"\x00" * (start_address - block_start)
            writeln(" [!] Flash program start address does not fall on block boundary.")
            writeln(" [!] Writing {0} pad bytes at start of block.".format(len(initial_pad)))

        else:
            initial_pad = b""

        with open(path, "rb") as file_fp:
            read_size = block_size
            # Start writing at block start address
            current_address = block_start
            # Pad the first read from the file, adjusted for the remaining size of the
            # block.
            chunk = initial_pad + file_fp.read(read_size - len(initial_pad))

            prog = Progress()
            while current_address < (start_address + data_size):
                kernel.flash_program(current_address, chunk,
                                     read_back_verify = True,
                                     program_callback = prog.program_cb,
                                     verify_callback  = prog.verify_cb)
                current_address += len(chunk)
                chunk = file_fp.read(read_size)

        writeln()

    def ram_kernel_flash_erase(self, kernel, options, args):
        erase_size = args[0]
        try:
            erase_size = int(erase_size, 0)

        except ValueError:
            raise ToolkitError("Invalid flash erase size %r!" % (erase_size,))

        if len(args) > 1:
            address = args[1]
            try:
                start_address = int(address, 0)

            except ValueError:
                raise ToolkitError("Invalid erase start address %r!" % (address,))

        else:
            writeln(" [*] Start address not specified; starting at block 0.")
            start_address = 0

        if erase_size < 0:
            raise ToolkitError("Erase size cannot be negative!")

        if start_address < 0:
            raise ToolkitError("Start address cannot be negative!")

        writeln(" [*] Erase %u bytes starting at 0x%08x." % (erase_size, start_address))

        def erase_cb(block_index, block_size):
            writeln("   [>] Erased block %d (size %d bytes)." % (block_index, block_size))

        kernel.flash_erase(start_address, erase_size, erase_callback = erase_cb)

    def run_application(self, filename, load_address):
        appl_stat = os.stat(filename)
        image_size = appl_stat.st_size
        def progcb(current, total):
            bar_len = 50
            bar_on = int(float(current) / total * bar_len)
            bar_off = bar_len - bar_on
            sys.stdout.write("   [%s%s] %u/%u B\r" % ("="*bar_on, " "*bar_off, current, total))
            sys.stdout.flush()

        with open(filename, "rb") as appl_fd:
            writeln(" [*] Loading application %r to 0x%08X..." % (filename, load_address))
            self.sbp.write_file(boot.FILE_TYPE_APPLICATION,
                                load_address, image_size, appl_fd, progress_callback = progcb)
            writeln(" [*] Application write/execute OK!")

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

def get_bsp_table(options):
    """ Load BSP config files as necessary, returning the combined BSP table. """
    if "nt" == os.name:
        user_dir = os.path.join(os.getenv("APPDATA"), "pyatk")

    else:
        user_dir = os.path.join(os.path.expanduser("~"), ".pyatk")

    if not os.path.exists(user_dir):
        writeln(" [i] Creating configuration directory...")
        os.makedirs(user_dir, 0o770)

    bsp_table_search_list = [
        os.path.join(user_dir, "bspinfo.conf"),
        options.bsp_config_file,
    ]

    try:
        return bspinfo.load_board_support_table(bsp_table_search_list)

    except IOError as err:
        writeln(" [!] Error loading BSP information table: %s" % (err,))
        writeln("    [*] Search paths:")
        for filename in bsp_table_search_list:
            writeln("    [-] %s" % (filename,))

        raise ToolkitError("Unable to load BSP information table.")

def main():
    def usage(error = None):
        sys.stderr.write("\nUsage: %s COMMAND [OPTIONS...]\n\n" % (sys.argv[0],))
        sys.stderr.write("  COMMAND = flash program -b BSP FILE  [ADDRESS=0]\n"
                         "            flash dump    -b BSP BYTES [ADDRESS=0]\n"
                         "            flash erase   -b BSP BYTES [ADDRESS=0]\n"
                         #"            flash test    -b BSP\n"
                         #"            memtest       -b BSP\n"
                         "            run -b BSP BINARY LOADADDR\n"
                         "            listbsp\n\n")

        if error:
            sys.stderr.write("Error: %s\n" % (error,))

        sys.exit(1)

    try:
        command = sys.argv[1]
        if command.lower() in ("-h", "help", "/?"):
            usage()

        args    = sys.argv[2:]
        atkprog = ToolkitApplication()
        atkprog.run(command, args)

    except boot.CommandResponseError as err:
        writeln(" <!> Bootloader response error: %s" % (err,))

    except IOError as err:
        sys.stderr.write(" [!] I/O error : %s\n" % (err,))
        traceback.print_tb(sys.exc_info()[2])
        sys.exit(1)

    except IndexError:
        usage("Missing COMMAND option!")

    except ToolkitError as exc:
        usage(str(exc))

if __name__ == "__main__":
    main()
