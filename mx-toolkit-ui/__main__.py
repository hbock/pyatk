import sys
import os
import time

from PySide.QtGui import QApplication, QMainWindow
from PySide.QtGui import QFileDialog

from PySide.QtGui import QValidator, QFont
from PySide.QtGui import QAbstractItemView
from PySide.QtGui import QDialogButtonBox
from PySide.QtCore import QAbstractTableModel
from PySide.QtCore import QModelIndex
from PySide.QtCore import Qt

from mainwindow import Ui_MainWindow

from pyatk import boot
from pyatk import ramkernel
from pyatk import bspinfo
# from pyatk.channel.uart import UARTChannel
# from serial.tools import list_ports

class AddressValidator(QValidator):
    """ Address text input validator for BSP memory addresses. """
    def __init__(self, minimum=0, maximum=0xffffffff):
        super(AddressValidator, self).__init__()
        self.min = minimum
        self.max = maximum

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
            if input_value in ("", "0x", "0b", "0o"):
                state = QValidator.Intermediate
            else:
                state = QValidator.Invalid

        return state

class BinaryFileHistoryTable(QAbstractTableModel):
    column_list = [
        "Filename",
        "Description",
        "Size",
        "Last Modified",
    ]
    def __init__(self, parent=None):
        super(BinaryFileHistoryTable, self).__init__(parent)
        self.file_list = []

    def columnCount(self, parent):
        return len(self.column_list)

    def rowCount(self, parent):
        return len(self.file_list)

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole and Qt.Horizontal == orientation:
            return self.column_list[section]

    def data(self, index, role):
        if Qt.DisplayRole == role:
            filename, description, stat = self.file_list[index.row()]
            column = index.column()
            ret = "NOPE"

            if 0 == column:
                ret = os.path.basename(filename)
            elif 1 == column:
                ret = description
            elif 2 == column:
                ret = stat.st_size
            elif 3 == column:
                timestamp = time.localtime(stat.st_mtime)
                ret = time.strftime("%Y-%m-%d %H:%M", timestamp)

            return ret

    def add_file(self, filename, description=""):
        try:
            file_stat = os.stat(filename)
            next_row = len(self.file_list)

            self.beginInsertRows(QModelIndex(), next_row, next_row)
            self.file_list.append((filename, description, file_stat))
            self.endInsertRows()

        except (IOError, OSError) as err:
            # TODO: show error message
            print("NOPE! %s" % (err,))

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

def get_bsp_table():
    """ Load BSP config files as necessary, returning the combined BSP table. """
    if "nt" == os.name:
        user_dir = os.path.join(os.getenv("APPDATA"), "pyatk")

    else:
        user_dir = os.path.join(os.path.expanduser("~"), ".pyatk")

    if not os.path.exists(user_dir):
        os.makedirs(user_dir, 0o770)

    bsp_table_search_list = [
        os.path.join(user_dir, "bspinfo.conf"),
        os.path.join(os.getcwd(), "bspinfo.conf"),
    ]

    return bspinfo.load_board_support_table(bsp_table_search_list)

class ToolkitMainWindow(QMainWindow):
    """ MX Toolkit UI main window """
    def __init__(self):
        super(ToolkitMainWindow, self).__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # self.memory_dump_model = StringHexTableModel(width = 8)
        self.addr_validator = AddressValidator()

        self.disable_all_the_things()
        self.setupui_bsp_select()
        self.setupui_binary_file_table()
        self.setupui_flash_tool()
        self.setupui_memory_tool()

    def disable_all_the_things(self):
        for widget in [
            self.ui.memory_operation_address_lineedit,
            self.ui.operation_address_lineedit,
            self.ui.operation_progress_bar,
        ]:
            widget.setEnabled(False)

        # This will be changed.
        self.ui.operation_progress_bar.setRange(0, 100)
        self.ui.operation_progress_bar.setValue(0)

    def connect_browse_to_lineedit(self, browse_button, lineedit, caption):
        """
        Connect a QPushButton to a QFileDialog for opening a single file.
        If the user selects a file, update the associated QLineEdit.
        """
        def do_browse():
            filename, _ = QFileDialog.getOpenFileName(
                parent=self,
                caption=caption
            )
            if filename:
                lineedit.setText(filename)

        browse_button.clicked.connect(do_browse)

    def setupui_flash_tool(self):
        self.ui.operation_address_lineedit.setValidator(self.addr_validator)
        self.ui.operation_length_lineedit.setValidator(self.addr_validator)

        self.ui.flash_tool_buttonbox.clear()
        self.flash_tool_go_button = self.ui.flash_tool_buttonbox.addButton(
            "Go", QDialogButtonBox.ActionRole
        )

    def setupui_memory_tool(self):
        self.ui.memory_operation_address_lineedit.setValidator(self.addr_validator)
        self.ui.memory_operation_length_lineedit.setValidator(self.addr_validator)
        self.ui.memory_tool_buttonbox.clear()
        self.memory_tool_go_button = self.ui.memory_tool_buttonbox.addButton(
            "Go", QDialogButtonBox.ActionRole
        )

    def setupui_binary_file_table(self):
        self.binary_file_table = BinaryFileHistoryTable(parent=self)
        self.ui.binary_file_history_tableview.setModel(self.binary_file_table)
        self.ui.binary_file_history_tableview.horizontalHeader().show()
        self.ui.binary_file_history_tableview.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        # TODO: resize on entry/removal
        self.ui.binary_file_history_tableview.resizeColumnsToContents()

        self.connect_browse_to_lineedit(
            self.ui.binary_file_browse_button,
            self.ui.binary_file_lineedit,
            "Select new binary file..."
        )

        self.ui.binary_file_table_add_button.clicked.connect(
            self.ui_add_binary_file
        )

    def ui_add_binary_file(self):
        filename = self.ui.binary_file_lineedit.text()
        if "" != filename:
            self.binary_file_table.add_file(filename)

    def get_selected_bsp_info(self):
        """
        Return the BoardSupportInfo instance corresponding to the
        selected BSP, including any custom RAM kernel information.
        """
        current_index = self.ui.bsp_select_combobox.currentIndex()
        selected_bsp_info = self.ui.bsp_select_combobox.itemData(current_index)

        if Qt.Checked == self.ui.bsp_custom_checkbox.checkState():
            ram_kernel_origin = int(self.ui.ram_kernel_origin_lineedit.text(), 0)
            ram_kernel_file = self.ui.ram_kernel_binary_lineedit.text()
            memory_init_file = self.ui.memory_init_lineedit.text()

            selected_bsp_info = bspinfo.BoardSupportInfo(
                "%s [Custom Kernel]" % (selected_bsp_info.description,),
                selected_bsp_info.base_memory_address,
                selected_bsp_info.memory_bottom_address,
                memory_init_file,
                ram_kernel_file,
                ram_kernel_origin,
                selected_bsp_info.usb_vid,
                selected_bsp_info.usb_pid,
            )

        return selected_bsp_info

    def setupui_bsp_select(self):
        """ Set up the device selection UI """
        bsp_table = get_bsp_table()

        self.connect_browse_to_lineedit(
            self.ui.memory_init_browse_button,
            self.ui.memory_init_lineedit,
            "Select BSP memory initialization file..."
        )

        self.connect_browse_to_lineedit(
            self.ui.ram_kernel_browse_button,
            self.ui.ram_kernel_binary_lineedit,
            "Select RAM kernel binary..."
        )

        self.ui.ram_kernel_origin_lineedit.setValidator(self.addr_validator)

        # For whatever reason, PySide does voodoo with namedtuples when converted
        # to a QVariant.  PySide docs imply it is supposed to opaquely handle any Python
        # type, but when converted back to a Python object it is a list.
        # If we instead wrap it in an "opaque" object, we can get the expected result.
        class OpaqueWrapper(object):
            def __init__(self, wrapped_object):
                self.wrapped = wrapped_object

        self.ui.bsp_select_combobox.currentIndexChanged[int].connect(self.ui_bsp_selection_changed)
        for bsp_name, bsp_info in bsp_table.iteritems():
            self.ui.bsp_select_combobox.addItem(u"[%s] %s" % (bsp_name, bsp_info.description),
                                                OpaqueWrapper(bsp_info))

        self.ui.bsp_custom_checkbox.stateChanged.connect(self.ui_bsp_custom_check_state_changed)
        self.ui_bsp_custom_check_state_changed(Qt.Unchecked)

    def ui_bsp_custom_check_state_changed(self, new_state):
        enable_custom_input = (Qt.Checked == new_state)

        for widget in [
            self.ui.ram_kernel_binary_lineedit,
            self.ui.ram_kernel_origin_lineedit,
            self.ui.memory_init_lineedit,
            self.ui.ram_kernel_browse_button,
            self.ui.memory_init_browse_button,
        ]:
            widget.setEnabled(enable_custom_input)

    def ui_bsp_selection_changed(self, index):
        """ The BSP selection combobox changed. """
        bsp_info = self.ui.bsp_select_combobox.itemData(index)
        # If we are in "Custom" mode, enable all widgets
        # for configuring the BSP.
        bsp_info = bsp_info.wrapped
        # Update the BSP information widgets.
        self.ui.memory_init_lineedit.setText(bsp_info.memory_init_file)
        self.ui.ram_kernel_binary_lineedit.setText(bsp_info.ram_kernel_file)
        self.ui.ram_kernel_origin_lineedit.setText("0x%08X" % (bsp_info.ram_kernel_origin,))

    #def _setupui_mbrowser_browser(self):
    #    """ Set up the bootstrap memory browser UI """
    #    self.ui.mbrowser_pp_datasize.addItem("Byte (8 bits)", boot.DATA_SIZE_BYTE)
    #    self.ui.mbrowser_pp_datasize.addItem("Half word (16 bits)", boot.DATA_SIZE_HALFWORD)
    #    self.ui.mbrowser_pp_datasize.addItem("Word (32 bits)", boot.DATA_SIZE_WORD)
    #
    #    self.ui.mbrowser_browse_datasize.addItem("Byte (8 bits)", boot.DATA_SIZE_BYTE)
    #    self.ui.mbrowser_browse_datasize.addItem("Half word (16 bits)", boot.DATA_SIZE_HALFWORD)
    #    self.ui.mbrowser_browse_datasize.addItem("Word (32 bits)", boot.DATA_SIZE_WORD)
    #
    #    # Snap the value of the read length to the nearest multiple of the browser
    #    # read size when the read size changes.
    #    def update_read_length_increment(index):
    #        datasize = int(self.ui.mbrowser_browse_datasize.itemData(index))
    #        if boot.DATA_SIZE_BYTE == datasize:
    #            new_increment = 1
    #        elif boot.DATA_SIZE_HALFWORD == datasize:
    #            new_increment = 2
    #        else:
    #            new_increment = 4
    #
    #        old_value = self.ui.mbrowser_browse_readlength.value()
    #        if old_value % new_increment != 0:
    #            # Snap to match new length alignment requirement
    #            self.ui.mbrowser_browse_readlength.setValue((old_value / new_increment) * new_increment)
    #
    #        self.ui.mbrowser_browse_readlength.setSingleStep(new_increment)
    #
    #    self.ui.mbrowser_browse_datasize.currentIndexChanged[int].connect(update_read_length_increment)
    #
    #    self.ui.mbrowser_browse_readlength.setMinimum(0x00000000)
    #    self.ui.mbrowser_browse_readlength.setMaximum(0x7FFFFFFF)
    #
    #    # Ensure the address is a valid address
    #    self.ui.mbrowser_browse_address.setValidator(self.bsp_addr_validator)
    #
    #    # Disable initially, until we actually complete a memory dump.
    #    self.ui.mbrowser_browse_save_button.setEnabled(False)
    #
    #    self.ui.mbrowser_browse_dump_table.setModel(self.memory_dump_model)
    #    self.ui.mbrowser_browse_dump_table.resizeColumnsToContents()
    #
    #    self.ui.mbrowser_browse_dump_button.clicked.connect(self.ui_mbrowser_dump_clicked)
    #
    #def ui_mbrowser_dump_clicked(self):
    #    start_address = int(self.ui.mbrowser_browse_address.text(), 0)
    #    read_length   = self.ui.mbrowser_browse_readlength.value()
    #    data_size     = int(self.ui.mbrowser_browse_datasize.itemData(self.ui.mbrowser_browse_datasize.currentIndex()))
    #
    #    if read_length == 0:
    #        # Nothing to read.
    #        return
    #
    #    # print "dump %u bytes bytes at %x, size %d" % (read_length, start_address, data_size)
    #    channel = self.channel()
    #    try:
    #        sbp = boot.SerialBootProtocol(channel)
    #        data = sbp.read_memory(start_address, data_size, read_length).tostring()
    #        self.memory_dump_model.set_data(data, start_address)
    #
    #    finally:
    #        channel.close()

def main():
    app = QApplication(sys.argv)
    mw = ToolkitMainWindow()
    mw.show()

    app.exec_()
    sys.exit()

if __name__ == "__main__":
    main()