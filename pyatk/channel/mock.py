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

    def queue_data(self, data):
        self.send_queue.append(data)

    def queue_rkl_response(self, ackcode, checksum, length, payload = ""):
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
        return_data = ""

        while len(return_data) < length and len(self.send_queue) > 0:
            new_data = self.send_queue.popleft()
            remaining_length = length - len(return_data)
            if remaining_length > len(new_data):
                return_data += new_data
            else:
                return_data += new_data[:remaining_length]
                self.send_queue.appendleft(new_data[remaining_length:])

        return return_data
