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
    with open(info_filename, "rb") as info_fp:
        reader = csv.reader(info_fp, dialect = "excel")
        # Consume and discard header.
        _ = reader.next()

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
