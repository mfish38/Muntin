
import ctypes
import ctypes.wintypes
import sys

from PySide2.QtCore import (
    Qt,
    Signal,
    QPoint,
    QEvent,
    QTimer,
    QRect
)

from PySide2.QtWidgets import (
    QApplication,
    QFrame,
    QSplitter,
    QVBoxLayout
)

from PySide2.QtGui import (
    QWindow,
    QPainter
)

import win32gui
import win32con

from window_capture import capture_window
from window_monitor import WindowMonitor

from hooks import MouseSignaler

user32 = ctypes.windll.user32


class Container(QFrame):
    mouse_over = Signal()

    def __init__(self, root):
        super().__init__()

        self._root = root
        self._handle = None
        self._sync_needed = False
        self._image = None

        root.moved.connect(self._sync_window)

        self.setMouseTracking(True)

        self._original_style = None

    def mouseMoveEvent(self, event):
        self.mouse_over.emit()

    def sync_needed(self):
        self._sync_needed = True

    def __del__(self):
        win32gui.SetWindowLong(self._handle, win32con.GWL_STYLE, self._original_style)

    def grab_window(self, window_handle):
        self._handle = window_handle

        style = win32gui.GetWindowLong(window_handle, win32con.GWL_STYLE)
        self._original_style = style

        # style &= ~win32con.WS_CAPTION
        style &= ~win32con.WS_THICKFRAME
        style |= win32con.WS_BORDER
        win32gui.SetWindowLong(window_handle, win32con.GWL_STYLE, style)

        # TODO: why does this break this?
        self._sync_needed = True
        self._sync_window()

    def _sync_window(self):
        if not self._root.moving and not self._sync_needed:
            return

        self._sync_needed = False

        size = self.size()
        pos = self.mapToGlobal(QPoint(0,0))

        user32.SetWindowPos(
            self._handle,
            self.effectiveWinId(),
            pos.x(),
            pos.y(),
            size.width(),
            size.height(),
            win32con.SWP_ASYNCWINDOWPOS #| win32con.SWP_HIDEWINDOW
        )

        self._image = capture_window(self._handle)

    def paintEvent(self, event):
        if self._image is None:
            return

        # TODO: performance here seems quite bad, causes window under to lag during moves, either hide the window or make this faster
        painter = QPainter(self)
        painter.drawImage(0, 0, self._image)

    def resizeEvent(self, event):
        self._sync_window()
        # self._image = capture_window(self._handle)

class WindowSplitter(QFrame):
    mouse_over = Signal()

    def __init__(self, root, orientation, overlap_monitor):
        super().__init__()

        self._overlap_monitor = overlap_monitor
        overlap_monitor.register(self)

        self._root = root

        splitter = QSplitter(orientation)
        self._splitter = splitter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(splitter)

        self.setLayout(layout)

        self._containers = {}

        self._entered_handle = None

        MouseSignaler.left_up.connect(self._left_mouse_up)

    def _left_mouse_up(self):
        entered_handle = self._entered_handle
        if entered_handle is None:
            return

        def function():
            self.add_window(entered_handle)
        QTimer.singleShot(0, function)
        # self.add_window(entered_handle)
        self._entered_handle = None

    def overlap_enter_event(self, handle, rectangle):
        if self._root.moving:
            return

        if handle in self._containers:
            return

        self._entered_handle = handle
        # self.add_window(handle)

    def overlap_move_event(self, handle, rectangle):
        if self._root.moving:
            return

        # print('move', handle)

    def overlap_exit_event(self, handle, rectangle):
        if self._root.moving:
            return

        # Don't remove the window unless it left being dragged.
        if not MouseSignaler.left_is_down:
            return

        self._entered_handle = None

        containers = self._containers
        if handle not in containers:
            return

        # this happens because after grabbing the window it is under the current which counts as an exit leave!!!
        # only exit if exits while the mouse is down?
        print('exiting?')

        self._root.remove_handle_to_move_under(handle)
        container = self._containers.pop(handle)
        container.deleteLater()

    def add_window(self, handle):
        self._root.add_handle_to_move_under(handle)
        container = Container(self._root)
        self._containers[handle] = container
        self._splitter.splitterMoved.connect(container.sync_needed)
        container.mouse_over.connect(self.mouse_over.emit)
        self._splitter.addWidget(container)
        container.grab_window(handle)

class Root(QFrame):
    moved = Signal()
    enter_size_move = Signal()
    exit_size_move = Signal()
    activation_change = Signal(bool)

    def __init__(self):
        super().__init__()

        self.moving = False

        self._handles = set()

        # def window_selector(handle, argument):
        #     class_name = win32gui.GetClassName(handle)
        #     title = win32gui.GetWindowText(handle)
        #     if class_name != "CabinetWClass":
        #         return
        #     # print(class_name, title)
        #     argument.append(handle)
        # argument = []
        # win32gui.EnumWindows(window_selector, argument)

        overlap_monitor = WindowMonitor()

        splitter = WindowSplitter(self, Qt.Vertical, overlap_monitor)

        # for handle in argument:
        #     self._handles.add(handle)
        #     splitter.add_window(handle)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self.setLayout(layout)

        splitter.mouse_over.connect(self._move_under)
        self.exit_size_move.connect(self._move_under)

        self.moving = False

    def add_handle_to_move_under(self, handle):
        self._handles.add(handle)

    def remove_handle_to_move_under(self, handle):
        self._handles.remove(handle)

    def changeEvent(self, event):
        if event.type() == QEvent.ActivationChange:
            self.activation_change.emit(self.isActiveWindow())

    def nativeEvent(
        self,
        event_type,
        message,
        _msg_from_address = ctypes.wintypes.MSG.from_address
    ):
        WM_ENTERSIZEMOVE = 0x0231
        WM_EXITSIZEMOVE = 0x0232

        message = _msg_from_address(int(message))

        if message.message == WM_ENTERSIZEMOVE:
            self.moving = True
            self.enter_size_move.emit()
        elif message.message == WM_EXITSIZEMOVE:
            self.moving = False
            self.exit_size_move.emit()

        return False

    def moveEvent(self, event):
        self.moved.emit()

    def _move_under(self):
        handles = self._handles

        if not handles:
            return

        # Get the z order
        def window_selector(handle, argument):
            if handle not in handles:
                return

            argument.append(handle)
        z_order = []
        win32gui.EnumWindows(window_selector, z_order)

        # Get the current window rectangle.
        # Note that this gives the wrong values:
        #   rect = self.frameGeometry()
        window_handle = self.effectiveWinId()
        left, top, right, bottom = win32gui.GetWindowRect(window_handle)

        # Move the window to under the last window
        user32.SetWindowPos(
            window_handle,
            z_order[-1],
            left,
            top,
            right - left,
            bottom - top,
            0
        )

# handle = user32.FindWindowW(u'Notepad', None)
app = QApplication(sys.argv)
window = Root()
window.resize(1000, 1000)
window.show()
app.exec_()
