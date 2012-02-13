import serial

class ATKChannel(object):
    def open(self):
        """
        Open the communication channel.
        """
        raise NotImplementedError()

    def close(self):
        """
        Close the communication channel.
        """
        raise NotImplementedError()
    
    def read(self, length):
        """
        Read ``length`` bytes from underlying ATK communication
        channel.
        """
        raise NotImplementedError()

    def write(self, data):
        """
        Write ``data`` binary string to underlying ATK communication
        channel.
        """
        raise NotImplementedError()    

class UARTChannel(ATKChannel):
    def __init__(self, port):
        super(UARTChannel, self).__init__()
        
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
