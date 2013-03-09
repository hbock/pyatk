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
import collections
import csv

#: A namedtuple for BSP information relevant to ATK.
BoardSupportInfo = collections.namedtuple(
    "BoardSupportInfo", (
        # The base memory address for the BSP.
        "base_memory_address",

        # The bottom of main memory for the BSP.
        "memory_bottom_address",

        # RAM kernel origin is typically (base_memory_address + 0x4000)
        # for the stock kernel's linker script (e.g., ram_kernel_mx53.lds).
        # This could be built differently for a custom design's BSP,
        # so we allow manually specifying it.
        "ram_kernel_origin",
    )
)
BSI = lambda *args: BoardSupportInfo._make(args)

def load_board_support_table(info_filename):
    """
    Load board support information from a CSV file with the following
    format:
    """
    with open(info_filename, "r") as info_fp:
        reader = csv.reader(info_fp, dialect = "excel")
        # Consume and discard header.
        _ = next(reader)

        new_bsp_table = collections.OrderedDict()
        for row in reader:
            if len(row) < 4:
                pass

            bsp_name = row[0]
            bsp_base_addr   = int(row[1], 0)
            bsp_bottom_addr = int(row[2], 0)
            bsp_ram_kernel_origin = int(row[3], 0)

            new_bsp_info = BSI(bsp_base_addr, bsp_bottom_addr, bsp_ram_kernel_origin)
            new_bsp_table[bsp_name] = new_bsp_info

        return new_bsp_table
