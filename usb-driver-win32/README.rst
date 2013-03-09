libusb-win32 driver
===================

This directory contains the ``libusb-win32`` driver and supporting library for
USB access on Windows. These are not specific to PyATK.  The included
INF file (imxusb.inf) contains support for the following i.MX processors:

- i.MX25
- i.MX27
- i.MX28
- i.MX31
- i.MX32
- i.MX35
- i.MX37
- i.MX50
- i.MX51 (TO1 and TO2)
- i.MX53

The ``libusb`` version distributed with PyATK is 1.2.6.0.

PyATK's authors provide no warranty or guarantee that PyATK or libusb
will not destroy your computer, introduce security vulnerabilities,
run over your dog, or set your house on fire.

If you have any issues with this release of ``libusb-win32``, please contact
the maintainer.  We will try to update our distribution of ``libusb-win32``
when issues crop up.

Installation and removal
------------------------

The x86 and amd64 drivers are included; ia64 is omitted, but if Itanium
support is desired, feel free to email the current maintainer. Currently
we are not providing an installer, but installation via Device Manager
is easy:

1. If Windows brings up the "Found New Hardware" dialog (XP/2003),
   select "Install from a list or specific location".

   On Windows Vista/7, find the device in "Device Manager".
   It should be under "Other Devices", with a name like "SE Blank SENNA"
   (SENNA is the internal name for the i.MX25). Open the device properties,
   click "Update Driver", and "Browse my computer for driver software."

#. Browse and find the usb-driver-win32 directory in the PyATK distribution
   or checkout.  Select this folder and click "Next".

#. On 64-bit machines, a warning will display that "Windows can't verify
   the publisher of this driver software".  ``libusb-win32`` is a self-signed
   driver, so it is not trusted by Windows.  Click "Install this driver
   software anyway" if you trust me!

#. Windows should successfully install the driver and identify your
   i.MX device as "i.MXyy Bootstrap".  You're all set!

For removal instructions, please see the official ``libusb-win32`` web
page [1].

LibUSB License
--------------

The LibUSB kernel driver is GPL.  We distribute the binary kernel driver
and userland component without modification; the source code for both
is freely available on the ``libusb-win32`` website [2].

[1] http://sourceforge.net/apps/trac/libusb-win32/wiki#Installation
[2] http://sourceforge.net/projects/libusb-win32/files/
