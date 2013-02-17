import sys
import re

from PySide.QtGui import QApplication, QMainWindow
from PySide.QtGui import QValidator, QFont
from PySide.QtCore import QAbstractTableModel, QModelIndex
from PySide.QtCore import Qt

from mainwindow import Ui_MainWindow

from pyatk import boot, ramkernel
from pyatk.channel.uart import UARTChannel

from serial.tools import list_ports

class BspAddressValidator(QValidator):
    """ Address text input validator for BSP memory addresses. """
    def __init__(self):
        super(BspAddressValidator, self).__init__()
        self.min = 0x00000100
        self.max = 0x1fffffff
        self.min_str = "0x%08x" % self.min
        self.max_str = "0x%08x" % self.max

    def fixup(self, input_value):
        if input_value == "":
            fixed = self.min_str
        else:
            int_value = int(input_value, 0)
            if int_value < self.min:
                fixed = self.min_str
            else:
                fixed = self.max_str

        return fixed

    def validate(self, input_value, pos):
        try:
            int_value = int(input_value, 0)
            if int_value < 0:
                state = QValidator.Invalid
            elif not (self.min <= int_value <= self.max):
                state = QValidator.Intermediate
            else:
                state = QValidator.Acceptable

        except ValueError:
            state = QValidator.Invalid

        return state

class PeekPokeHistoryModel(QAbstractTableModel):
    """ A table model for displaying the peek/poke operation history. """
    def __init__(self):
        super(PeekPokeHistoryModel, self).__init__()
        self.history_list = [
            # TODO: remove test data
            (0, 0xdeadbeef, 0x12),
            (1, 0xcafecafe, 0xfeed),
        ]

    def add_operation(self, op, address, value):
        self.history_list.append((op, address, value))

    def columnCount(self, parent):
        return 3

    def rowCount(self, parent):
        return len(self.history_list)

    def data(self, index, role):
        value = None
        if role == Qt.DisplayRole:
            row = index.row()
            col = index.column()

            value = self.history_list[row][col]
            if col == 0:
                value = "Peek" if value == 0 else "Poke"
            else:
                value = "0x%08X" % int(value)

        return value

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                if section == 0:
                    return "Operation"
                elif section == 1:
                    return "Address"
                elif section == 2:
                    return "Value"
            else:
                return str(section + 1)

class StringHexTableModel(QAbstractTableModel):
    def __init__(self, width = 8):
        super(StringHexTableModel, self).__init__()
        self.width = width
        self.byte_data = ""
        self.start_address = 0
        self.set_data("i.MX toolkit \x02\x03 test" * 50, 0xfeedcafe)
        self.font = QFont("Monospace")
        self.font.setStyleHint(QFont.TypeWriter)

    def set_data(self, byte_data, start_address):
        """ Set model data, re-assign columns/rows, and signal a model reset """
        self.byte_data = byte_data
        self.start_address = start_address
        self.row_count = max(1, len(byte_data) / self.width)

        self.reset()

    def rowCount(self, parent):
        return self.row_count

    def columnCount(self, parent):
        # Hex, ASCII display columns with one spacer column
        return 2 * self.width + 1

    def data(self, index, role):
        value = None
        if role == Qt.DisplayRole:
            row = index.row()
            col = index.column()

            try:
                # Show ASCII value (if not printable, show ".") beside hex representation
                if col > self.width:
                    true_col = (col - self.width - 1)
                    value = self.byte_data[self.width * row + true_col]
                    if not (0x1F <= ord(value) <= 0x7F):
                        value = "."

                # Show hex representation
                elif col < self.width:
                    byte = self.byte_data[self.width * row + col]
                    value = "%02x" % ord(byte)

            except IndexError:
                pass

        elif role == Qt.FontRole:
            return self.font

        # All values should be centered.
        elif role == Qt.TextAlignmentRole:
            value = Qt.AlignCenter

        return value

    def headerData(self, section, orientation, role):
        """
        Show the header for the hex dump view.
        """
        value = None
        if role == Qt.DisplayRole:
            # Horizontal = column address within row
            if orientation == Qt.Horizontal:
                if section < self.width:
                    value = "%X" % section
                elif section > self.width:
                    value = "%X" % (section - self.width - 1)

            # Vertical = row address
            else:
                base_address = self.start_address + (section * self.width)
                upper_word = ((base_address & 0xFFFF0000) >> 16)
                lower_word = (base_address & 0x0000FFFF)

                value = "%04x %04x" % (upper_word, lower_word)

        # Header should be centered.
        elif role == Qt.TextAlignmentRole:
            value = Qt.AlignCenter

        return value

class ToolkitMainWindow(QMainWindow):
    """ i.MX Toolkit main window """
    def __init__(self):
        super(ToolkitMainWindow, self).__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.memory_dump_model = StringHexTableModel(width = 8)
        self.bsp_addr_validator = BspAddressValidator()

        self._setupui_dev_select()
        self._setupui_mbrowser_peekpoke()
        self._setupui_mbrowser_browser()

    def _setupui_dev_select(self):
        """ Set up the device selection UI """

        ## Serial port enumeration
        serial_ports = list_ports.comports()
        for port_name, description, hardware_id in serial_ports:
            desc = port_name
            if description:
                desc += " (%s)" % description

            self.ui.dev_select_combo.addItem(desc, port_name)

        ## TODO: USB

    def _setupui_mbrowser_peekpoke(self):
        self.pp_history_model = PeekPokeHistoryModel()
        self.ui.mbrowser_pp_table.setModel(self.pp_history_model)
        self.ui.mbrowser_pp_address.setValidator(self.bsp_addr_validator)

    def _setupui_mbrowser_browser(self):
        """ Set up the bootstrap memory browser UI """
        self.ui.mbrowser_pp_datasize.addItem("Byte (8 bits)", boot.DATA_SIZE_BYTE)
        self.ui.mbrowser_pp_datasize.addItem("Half word (16 bits)", boot.DATA_SIZE_HALFWORD)
        self.ui.mbrowser_pp_datasize.addItem("Word (32 bits)", boot.DATA_SIZE_WORD)

        self.ui.mbrowser_browse_datasize.addItem("Byte (8 bits)", boot.DATA_SIZE_BYTE)
        self.ui.mbrowser_browse_datasize.addItem("Half word (16 bits)", boot.DATA_SIZE_HALFWORD)
        self.ui.mbrowser_browse_datasize.addItem("Word (32 bits)", boot.DATA_SIZE_WORD)

        # Snap the value of the read length to the nearest multiple of the browser
        # read size when the read size changes.
        def update_read_length_increment(index):
            datasize = int(self.ui.mbrowser_browse_datasize.itemData(index))
            if boot.DATA_SIZE_BYTE == datasize:
                new_increment = 1
            elif boot.DATA_SIZE_HALFWORD == datasize:
                new_increment = 2
            else:
                new_increment = 4

            old_value = self.ui.mbrowser_browse_readlength.value()
            if old_value % new_increment != 0:
                # Snap to match new length alignment requirement
                self.ui.mbrowser_browse_readlength.setValue((old_value / new_increment) * new_increment)

            self.ui.mbrowser_browse_readlength.setSingleStep(new_increment)

        self.ui.mbrowser_browse_datasize.currentIndexChanged[int].connect(update_read_length_increment)

        self.ui.mbrowser_browse_readlength.setMinimum(0x00000000)
        self.ui.mbrowser_browse_readlength.setMaximum(0x7FFFFFFF)

        # Ensure the address is a valid address
        self.ui.mbrowser_browse_address.setValidator(self.bsp_addr_validator)

        # Disable initially, until we actually complete a memory dump.
        self.ui.mbrowser_browse_save_button.setEnabled(False)

        self.ui.mbrowser_browse_dump_table.setModel(self.memory_dump_model)
        self.ui.mbrowser_browse_dump_table.resizeColumnsToContents()

        self.ui.mbrowser_browse_dump_button.clicked.connect(self.ui_mbrowser_dump_clicked)

    def ui_mbrowser_dump_clicked(self):
        start_address = int(self.ui.mbrowser_browse_address.text(), 0)
        read_length   = self.ui.mbrowser_browse_readlength.value()
        data_size     = int(self.ui.mbrowser_browse_datasize.itemData(self.ui.mbrowser_browse_datasize.currentIndex()))

        if read_length == 0:
            # Nothing to read.
            return

        # print "dump %u bytes bytes at %x, size %d" % (read_length, start_address, data_size)
        channel = self.channel()
        try:
            sbp = boot.SerialBootProtocol(channel)
            data = sbp.read_memory(start_address, data_size, read_length).tostring()
            self.memory_dump_model.set_data(data, start_address)

        finally:
            channel.close()

    def channel(self):
        """ Open and return the user-selected channel. """
        port = self.ui.dev_select_combo.itemData(self.ui.dev_select_combo.currentIndex())
        channel = UARTChannel(port)
        channel.open()
        return channel

def main():
    app = QApplication(sys.argv)
    mw = ToolkitMainWindow()
    mw.show()

    app.exec_()
    sys.exit()

if __name__ == "__main__":
    main()