# Copyright (c) 2012-2013, Harry Bock <bock.harryw@gmail.com>
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

import sys
import collections
if sys.version_info > (3, 0):
    from configparser import ConfigParser
    from configparser import NoOptionError
# Python 2.x support
else:
    from ConfigParser import SafeConfigParser as ConfigParser
    from ConfigParser import NoOptionError


#: A namedtuple for BSP information relevant to ATK.
BoardSupportInfo = collections.namedtuple(
    "BoardSupportInfo", (
        # Long description of the board
        "description",

        # The base memory address for the BSP.
        "base_memory_address",

        # The bottom of main memory for the BSP.
        "memory_bottom_address",

        # The memory initialization file for this BSP.
        # If it is not available, it will be set to None.
        "memory_init_file",

        # The RAM kernel file itself.  If this is not specified,
        # it will be None.
        "ram_kernel_file",

        # RAM kernel origin is typically (base_memory_address + 0x4000)
        # for the stock kernel's linker script (e.g., ram_kernel_mx53.lds).
        # This could be built differently for a custom design's BSP,
        # so we allow manually specifying it.
        "ram_kernel_origin",

        # USB vendor ID
        "usb_vid",
        # USB product ID
        "usb_pid",
    )
)
BSI = lambda *args: BoardSupportInfo._make(args)

def load_board_support_table(info_filename_list):
    """
    Load board support information from one of the CSV files in
    ``info_filename_list``.

    If no files in ``info_filename_list`` were able to be parsed,
    :exc:`IOError` is raised.
    """
    reader = ConfigParser()
    success_list = reader.read(info_filename_list)
    if not success_list:
        raise IOError("No suitable configuration files found.")

    new_bsp_table = collections.OrderedDict()
    for section in reader.sections():
        def getint(key):
            return int(reader.get(section, key), 0)

        bsp_name = section
        bsp_desc = reader.get(section, "description")

        try:
            ram_kernel_file = reader.get(section, "ram_kernel_file")
        except NoOptionError:
            ram_kernel_file = None

        try:
            memory_init_file = reader.get(section, "memory_init_file")
        except NoOptionError:
            memory_init_file = None

        bsp_base_addr = getint("sdram_start")
        bsp_bottom_addr = getint("sdram_end")
        bsp_ram_kernel_origin = getint("ram_kernel_origin")

        bsp_usb_vid = getint("usb_vid")
        bsp_usb_pid = getint("usb_pid")

        new_bsp_info = BSI(
            bsp_desc,
            bsp_base_addr,
            bsp_bottom_addr,
            memory_init_file,
            ram_kernel_file,
            bsp_ram_kernel_origin,
            bsp_usb_vid,
            bsp_usb_pid,
        )

        new_bsp_table[bsp_name] = new_bsp_info

    return new_bsp_table
