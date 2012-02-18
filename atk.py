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

import os
import sys
import time
from pprint import pprint
from optparse import OptionParser

from pyatk import channel
from pyatk import boot
from pyatk import rkl

DEFAULT_RAM_KERNEL_ADDRESS = 0x80004000

def run_atk(channel, options):
    sbp = boot.SerialBootProtocol(channel)
    ramkernel = rkl.RAMKernelProtocol(channel)

    if options.init_file:
        initdata = read_initialization_file(options.init_file)
    else:
        if options.ram_kernel_file:
            parser.error("RAM kernel selected, but initialization file missing.")

        initdata = []

    try:
        status = sbp.get_status()
        print "Boot status: 0x%02X" % status

        # Initial memory test
        sbp.write_memory(0x78001000, boot.DATA_SIZE_WORD, 0xBEEFDEAD)
        check = sbp.read_memory(0x78001000, boot.DATA_SIZE_WORD)
        if 0xBEEFDEAD != check:
            print "ERROR: SRAM write check failed: got 0x%08X" % check        

        sbp.write_memory(0x78001000, boot.DATA_SIZE_WORD, 0xBEEFCAFE)
        check = sbp.read_memory(0x78001000, boot.DATA_SIZE_WORD)
        if 0xBEEFCAFE != check:            
            print "ERROR: SRAM write check failed: got 0x%08X" % check

        for initaddr, initval, initwidth in initdata:
            print "init: write 0x%08X to 0x%08X" % (initval, initaddr)
            sbp.write_memory(initaddr, initwidth, initval)
        
        if options.ram_kernel_file is not None:
            rk_stat = os.stat(options.ram_kernel_file)
            with open(options.ram_kernel_file, "rb") as rk_fp:
                print "writing ram kernel %r to 0x%08X" % (options.ram_kernel_file,
                                                           options.ram_kernel_address)
                sbp.write_file(boot.FILE_TYPE_APPLICATION, options.ram_kernel_address,
                               rk_stat.st_size, rk_fp)
                sbp.complete_boot()
                print "RAM kernel write/execute OK!"
                
    except boot.CommandResponseError, e:
        print "Command response error: %s" % e

    if options.ram_kernel_file is not None:
        print "waiting after ram kernel write..."
        time.sleep(1)

        print "ram kernel getver:"
        ramkernel.getver()
        print "resetting CPU"
        ramkernel.reset()
        time.sleep(1)
        print "status after reset: 0x%08X" % sbp.get_status()

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
    parser = OptionParser("%prog -s DEVICE [-r ramkernel] [-i init.txt] [application]")
    parser.add_option("--initialization-file", "-i", action = "store",
                      dest = "init_file", metavar = "FILE",
                      help = "Register initialization file.")
    parser.add_option("--ram-kernel", "-r", action = "store",
                      dest = "ram_kernel_file", metavar = "FILE",
                      help = "RAM kernel helper application binary.")
    parser.add_option("--ram-kernel-address", "-a", action = "store",
                      dest = "ram_kernel_address", type = "int", metavar = "ADDRESS",
                      default = DEFAULT_RAM_KERNEL_ADDRESS,
                      help = ("RAM kernel helper application base address "
                              "(default DRAM 0x%08X)." % DEFAULT_RAM_KERNEL_ADDRESS))
    parser.add_option("--serialport", "-s", action = "store",
                      dest = "serialport", metavar = "DEVICE",
                      help = "Serial port device name.")
    
    options, args = parser.parse_args()

    if not options.serialport:
        parser.error("Please select a serial port.")

    serial_channel = channel.UARTChannel(options.serialport)
    serial_channel.open()

    try:
        run_atk(serial_channel, options)

    except IOError, e:
        print "I/O error: %s" % e

    finally:
        serial_channel.close()

if __name__ == "__main__":
    main()
