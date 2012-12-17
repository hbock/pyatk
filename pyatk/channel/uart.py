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

import serial

from pyatk.channel import base

class UARTChannel(base.ATKChannelI):
    def __init__(self, port):
        super(UARTChannel, self).__init__()

        self._ramkernel_channel_type = base.CHANNEL_TYPE_UART

        self.port = None
        port = serial.serial_for_url(port, do_not_open = True)
        port.baudrate = 115200
        port.parity   = serial.PARITY_NONE
        port.stopbits = serial.STOPBITS_ONE
        port.bytesize = serial.EIGHTBITS
        port.timeout  = 0.5
        port.rtscts   = False
        port.xonxoff  = False
        port.dsrdtr   = False

        self.port = port

    def open(self):
        self.port.open()

    def close(self):
        self.port.close()
        
    def write(self, data):
        self.port.write(data)

    def read(self, length):
        return self.port.read(length)
