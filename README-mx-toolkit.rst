``mx-toolkit`` - i.MX Processor Bootstrap Toolkit
===================================================

``mx-toolkit`` is command line program aimed at replacing the
Advanced Toolkit (ATK) program distributed by Freescale
Semiconductor for their i.MX series processors.

This project is in no way affiliated with or supported by Freescale
Semiconductor.  For official support, you must use their officially
supplied tool.  Do not contact Freescale about this program.

See the README.rst file for more information on supported processors,
background, etc.

BSP Configuration - Initialization files, RAM kernels, etc.
-----------------------------------------------------------

``mx-toolkit`` understands a BSP (Board Support Package) configuration
file.  It is an INI format configuration file.  The default search locations
for "bspinfo.conf" are:

 * %APPDATA%\\pyatk\\bspinfo.conf (Windows)
 * ~/.pyatk/bspinfo.conf (UNIX)
 * The current working directory (all platforms)

Alternatively, you can manually set the BSP configuration file with the -c option::

  local:~/project $ mx-toolkit.py -c ~/boards/mybsp.conf listbsp

The BSP configuration file pulls together several pieces of information
required to bootstrap a given board or i.MX processor family:

 * Start address of SDRAM
 * End address of SDRAM (inclusive)
 * USB VID and PID for the bootstrap mode of the i.MX processor
 * Origin (start address) of RAM kernel
 * RAM kernel binary file (optional)
 * Memory initialization file (optional)

The SDRAM range and USB VID/PID generally will not change from board
to board with the same i.MX processor family (e.g., i.MX258).  However,
you are free to compile the ATK RAM kernel to start at any address.
To create a new BSP type 'fnop5643' based on the i.MX25, create a
new entry at the end of your "bspinfo.conf"::

 [fnob5643]
 description = Frob Your NOPs
 sdram_start = 0x80000000
 sdram_end = 0x8FFFFFFF
 memory_init_file = D:\mDDR_mem_init.txt
 ram_kernel_file = D:\mx25_nand.bin
 ram_kernel_origin = 0x82005643
 usb_vid = 0x15a2
 usb_pid = 0x003a

In this example, the 'fnob5643' BSP uses a RAM kernel that was compiled
to start at 0x82005643 in SDRAM. It uses the standard USB VID and PID for
the i.MX25 bootstrap ROM.

Running ``mx-toolkit``
------------------------

The examples below assume you are running on Linux, but they should run fine
on Windows and Mac OS X assuming you substitute in the proper path structure
for your operating system.   It also assumes the "mx-toolkit.py" script is
in your PATH.

All invocations of ``mx-toolkit`` using commands other than "listbsp" must
include the BSP name of your board in "bspinfo.conf" with the ``-b`` option::

 local:~/project $ mx-toolkit.py COMMAND -b mx25


If you wish to specify a memory initialization file manually,
add the path to this file with the ``-i`` switch::

 local:~/project $ mx-toolkit.py COMMAND -b mx25 -i mDDR_init.txt

The memory initialization file must contain a memory initialization
sequence in the same format as the ATK tool; one memory address per
line, with the value and access width in bits::

 # Start of mDDR initialization
 # Write a 32-bit quantity 0x00000004 to address 0xb8001010
 0xB8001010 0x00000004 32
 0xB8001004 0x002ddb3a 32
 0xb8001000 0x93210080 32
 # Write a 16-bit quantity 0x1234 to 0x80000400 in SDRAM
 0x80000400 0x1234 16
 # Write an 8-bit quantity 0xa3 to 0xb8001000
 0xb8001000 0xa3 8
 0x80000000 0x12344321 32

The contents of this file will vary from board to board depending on your
SDRAM banks, timing, and i.MX processor.  Consult your local EE for help.

Loading applications into SRAM or SDRAM
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``mx-toolkit`` can load and execute applications directly in memory
without the need for a RAM kernel.  This is useful for trivial bringup
tasks and for debugging a new RAM kernel flash implementation, for example.

To write and execute an application binary to memory address 0x80001234,
run the following command::

  local:~/project $ mx-toolkit.py run -b mx25 APPL.BIN 0x80001234


Writing application into flash memory
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``mx-toolkit`` can also work with flash memory, including the ability to
program flash memory from an arbitrary address.  To do this, you must provide
the tool with a RAM kernel binary that supports your board and flash memory
device.  If you do not already have an appropriate RAM kernel binary,
please refer to Freescale's manual and source code for building
a RAM kernel for your i.MX processor family.  You can specify the RAM kernel
to use via the "bspinfo.conf" file above, or manually via the "-k" command-line
switch.

It is important to note that for some flash parts (NAND comes to mind),
``mx-toolkit`` will likely only work if you are writing to the start
of a block.  This is because you must erase the flash part before you
program it, and the erase option generally only operates at the block
level (e.g., 128kB at a time).

To program your flash part "mx25" starting at block 0 with file "APPLICATION.ROM",
run the following command::

  local:~/project $ mx-toolkit.py flash program -b mx25 APPLICATION.ROM 0

Depending on the speed of your flash part and the size of APPLICATION.ROM,
this make take some time.  ``mx-toolkit`` will erase, program, and verify
each block of flash until it has written all of APPLICATION.ROM.

``mx-toolkit`` provides no confirmation of its actions and will happily
erase your device with reckless abandon.  Please take care!

Reading/dumping flash memory
----------------------------

``mx-toolkit`` can also leverage the RAM kernel to dump flash memory.
The following command will dump 1 kB of a flash device, starting at address
0x20000 (block 1 of a part with 128 kB blocks)::

  local:~/project $ mx-toolkit.py flash dump -b mx25 1024 0x20000

The command will dump the block to the screen in combined hex+ASCII format,
and also dump the data directly to "dump.bin".

Erasing flash memory
----------------------------

``mx-toolkit`` can also leverage the RAM kernel to erase flash memory.
The following command will erase 128 kB of a flash device, starting at address
0 (block 0 of a part with 128 kB blocks)::

  local:~/project $ mx-toolkit.py flash erase -b mx25 0x20000

NOTE: Although the tool will let you erase less than the block size of
the flash part, be aware that your RAM kernel will likely need to erase
the entire block anyway.  This is an inherent property of NAND flash.