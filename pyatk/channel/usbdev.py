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
PyUSB ATK communications channel implementation.  Supports
libusb-0.1, libusb-1.0, libusbx, and OpenUSB.

Requires PyUSB 1.0.
"""
import usb.core
import usb.util
from pyatk.channel import base

VID_FREESCALE = 0x15a2

class USBChannel(base.ATKChannelI):
    """
    USB ATK channel implementation.
    """
    def __init__(self, idVendor = VID_FREESCALE, idProduct = None):
        """
        Prepare to connect to USB channel with vendor ID ``idVendor``
        and product ID ``idProduct``.  If ``idProduct`` is ``None``, match
        any device with ``idVendor``.

        The default ``idVendor`` is Freescale Semiconductor (``0x15a2``).
        """
        super(USBChannel, self).__init__()

        # The RAM kernel expects the channel type variable to be set to 1
        # if the UART channel is used.
        self._ramkernel_channel_type = base.CHANNEL_TYPE_USB

        if idVendor is None:
            raise ValueError("Vendor ID argument cannot be None!")

        self.vid = idVendor
        self.pid = idProduct

        self.dev = None
        self.interface = None
        self.endpoint_in = None
        self.endpoint_out = None
        self.configuration = None

        self.internal_read_buffer = b""

        self.write_timeout = 2000 # ms
        self.read_timeout = 1000 # ms

    def open(self):
        # Setting idProduct = None doesn't work at all.
        # Just don't pass idProduct if we don't want to match it.
        kwargs = {}
        if self.pid is not None:
            kwargs["idProduct"] = self.pid

        # Find all devices matching the specified VID/PID.
        dev_list = usb.core.find(True, idVendor = self.vid, **kwargs)

        # We only accept one device.  If there are more than one
        # matching device, we have to bail - they all have the same
        # serial number!
        if len(dev_list) == 1:
            dev = dev_list[0]
            # Just set the default configuration - there is only one.
            dev.set_configuration()
            self.configuration = dev.get_active_configuration()
            # Dump information about the interface...
            #for intf in cfg:
            #    print "bInterfaceNumber", intf.bInterfaceNumber
            #    print "bAlternateSetting", intf.bAlternateSetting
            #    print
            self.interface = usb.util.find_descriptor(
                self.configuration,
                bInterfaceNumber = 0,
                bAlternateSetting = 0
            )
            # OUT endpoint
            self.endpoint_out = usb.util.find_descriptor(
                self.interface,
                custom_match = lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
            )
            if self.endpoint_out is None:
                raise IOError("Could not find OUT endpoint for USB device.")

            #print "wMaxPacketSize", self.endpoint_out.wMaxPacketSize
            #print "bLength", self.endpoint_out.bLength

            # IN endpoint
            self.endpoint_in = usb.util.find_descriptor(
                self.interface,
                custom_match = lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
            )
            if self.endpoint_in is None:
                raise IOError("Could not find IN endpoint for USB device.")

            #print "wMaxPacketSize", self.endpoint_in.wMaxPacketSize
            #print "bLength", self.endpoint_in.bLength

            self.dev = dev

        # Don't allow open() to connect to multiple devices.
        elif len(dev_list) > 1:
            raise IOError("Multiple devices matched. Please only connect one matching "
                          "USB device.")

        # No devices matched.
        else:
            raise IOError("Unable to enumerate device. Is it connected and in "
                          "serial boot mode?")

    def close(self):
        """
        Close the USB interface.
        """
        # Removing all references to endpoints, interfaces,
        # and device instances should release any claims
        # on the USB interface.
        self.configuration = None
        self.endpoint_out = None
        self.endpoint_in = None
        self.interface = None
        self.dev = None

    def write(self, data):
        max_packet_size = self.endpoint_out.wMaxPacketSize
        bytes_written = 0
        while bytes_written < len(data):
            pkt = data[bytes_written:bytes_written + max_packet_size]
            try:
                self.endpoint_out.write(pkt, timeout = self.write_timeout)
                bytes_written += len(pkt)
            except usb.USBError as e:
                raise IOError(str(e))

    def read(self, length):
        # Append to internal read buffer until we've received enough
        # packets from the IN endpoint.
        #
        while len(self.internal_read_buffer) < length:
            try:
                # We can only read the size of the max packet size for
                # the read endpoint...
                data = self.endpoint_in.read(64, timeout = self.read_timeout).tostring()
                #print "received", repr(data)
                ## Buffer internally, since we may get more data than
                ## we are expecting.
                self.internal_read_buffer += data

            except usb.USBError as e:
                raise IOError(str(e))

        # pull off the requested amount of data, if we did not time out.
        return_data = self.internal_read_buffer[:length]
        self.internal_read_buffer = self.internal_read_buffer[length:]

        return return_data
