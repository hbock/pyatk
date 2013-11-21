``pyATK`` - Python implementation of the Freescale Advanced Toolkit
===================================================================

``pyATK`` (Python ATK) is an attempt at replacing the Advanced Toolkit
(ATK) program distributed by Freescale Semiconductor for their i.MX
series processors.

pyATK is a Python library (supporting 2.6+) that allows you to
develop custom bootstrap tools for i.MX processors.  It also
comes with a command-line and GUI utility for common operations,
doubling as a useful API example.

This project is in no way affiliated with or supported by Freescale
Semiconductor.  For official support, you must use their officially
supplied tool.  Do not contact Freescale about this program.

Current i.MX processor support
------------------------------

This project is in early development, and currently targets the
i.MX25 platform.  While the program attempts support for other
i.MX processors, the author does not have access to these chips
and cannot test them.

You are welcome to provide the project maintainer(s) with test
devices to provide or fix support for your particular PDK. As
always, if you have devices you can test and can add support yourself,
patches are welcome!

Serial Boot Protocol
--------------------

The serial boot protocol is a protocol exposed by the i.MX boot ROM.
Consult the i.MX RM for your design for how to enter the CPU boot ROM.

pyATK supports the serial boot protocol out of the box, allowing you
to execute test applications directly, as well as read and write
memory for initialization purposes.  The boot ROM supports the HAB
secure boot framework, but this is not currently implemented in pyATK.

In order to access the SDRAM used in your design, you must provide a
memory initialization file that sets up the SDRAM controller with
proper timings.  Currently, no example initialization files are
provided with pyATK; some are provided with the stock Freescale ATK
installation (none are included in the ATK source code!).  pyATK
directly supports initialization files used with the Freescale ATK.

i.MX RAM Kernel
---------------

The serial boot protocol ROM has no concept of any flash device on the
board. In order to make it simple to program your application into
MMC, NOR, or NAND, the ATK uses the concept of the "RAM Kernel" to
abstract away device flash operation.

The ATK source code contains a RAM kernel that can be extended for
your design's flash chip (NAND, MMC, eSDHC, etc.).  The ATK
program loads and executes this kernel in SDRAM, exposing the RAM
kernel protocol for unified flash identification, erase, programming,
etc.

The pyATK implementation supports the protocol exposed by Freescale's
default RAM kernel implementation, but does not provide any
implementation of the kernel itself.
If your design has a custom NAND flash chip unknown to the stock ATK
RAM kernels, you must compile your own using the source code provided
on the Freescale website.  Freescale provides an excellent manual for
adapting the RAM kernel to your design[1].  This manual also documents
the RAM kernel protocol.

References
----------
[1] I.MX Platform Advanced Toolkit Reference Manual
