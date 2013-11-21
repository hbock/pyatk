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
import struct
import collections

from pyatk.channel.base import ATKChannelI

class MockChannel(ATKChannelI):
    """
    A channel designed for testing protocol handlers.
    """
    def __init__(self):
        super(MockChannel, self).__init__()

        # Data collected from write() calls, in order.
        self.recv_data = []
        # Buffered data to be sent to the calling host.
        self.send_queue = collections.deque()

    def get_data_written(self):
        return b"".join(self.recv_data)

    def queue_data(self, data):
        self.send_queue.append(data)

    def queue_rkl_response(self, ackcode, checksum, length, payload = b""):
        """
        Queue up an RKL response to send.
        """
        command = struct.pack(">hHI", ackcode, checksum, length)
        self.queue_data(command)
        if payload:
            self.queue_data(payload)

    def write(self, data):
        """
        Capture data written to this channel
        """
        self.recv_data.append(data)

    def read(self, length):
        """
        Read up to length bytes of buffered data from this channel.
        """
        return_data = b""

        while len(return_data) < length and len(self.send_queue) > 0:
            new_data = self.send_queue.popleft()
            remaining_length = length - len(return_data)
            if remaining_length > len(new_data):
                return_data += new_data
            else:
                return_data += new_data[:remaining_length]
                self.send_queue.appendleft(new_data[remaining_length:])

        return return_data
