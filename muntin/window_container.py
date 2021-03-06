
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

        root.moved.connect(self._moved)
        root.resized.connect(self._resized)

        self.setMouseTracking(True)

        self._original_style = None

        root.exit_size_move.connect(self._exit_size_move)

        self._hidden = False

    def _moved(self):
        # Don't do anything if already hidden
        if self._hidden:
            return

        # Get new window position and size.
        size = self.size()
        pos = QPoint(0, -self.height())

        # Save an image to display on the container in place of the window.
        self._image = capture_window(self._handle)

        # Hide the window.
        user32.SetWindowPos(
            self._handle,
            self.effectiveWinId(),
            pos.x(),
            pos.y(),
            size.width(),
            size.height(),
            win32con.SWP_ASYNCWINDOWPOS #| win32con.SWP_HIDEWINDOW
        )

        self._hidden = True

    def _resized(self):
        self._sync_window()

    def _exit_size_move(self):
        self._sync_window()

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

        self._sync_needed = True
        self._sync_window()

    def sync_soon(self):
        '''
        Adds a window sync to the event loop.
        '''
        QTimer.singleShot(0, self._sync_window)

    def _sync_window(self):
        if self._root.is_moving:
            return

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
        self._hidden = False

    def paintEvent(self, event):
        if self._image is None:
            return

        # TODO: performance here seems quite bad, causes window under to lag during moves, either hide the window or make this faster
        painter = QPainter(self)
        painter.drawImage(0, 0, self._image)

    def resizeEvent(self, event):
        self._sync_window()

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

        # Need to add the window later so that its no longer being positioned.
        def function():
            self.add_window(entered_handle)
        QTimer.singleShot(0, function)

        self._entered_handle = None

    def overlap_enter_event(self, handle, rectangle, widget_rectangle):
        if self._root.is_moving or self._root.is_resizing:
            return

        if handle in self._containers:
            return

        self._entered_handle = handle
        # self.add_window(handle)

    def overlap_move_event(self, handle, rectangle, widget_rectangle):
        if self._root.is_moving or self._root.is_resizing:
            return

        # print('move', handle)

    def overlap_exit_event(self, handle, rectangle, widget_rectangle):
        if self._root.is_moving or self._root.is_resizing:
            return

        # Don't remove the window due to z-order changes.
        if rectangle.intersects(widget_rectangle):
            return

        # Don't remove the window unless it left being dragged.
        if not MouseSignaler.left_is_down:
            return

        # print('exit')

        self._entered_handle = None

        containers = self._containers
        if handle not in containers:
            return

        self._root.remove_handle_to_move_under(handle)
        container = self._containers.pop(handle)
        container.deleteLater()

    def add_window(self, handle):
        self._root.add_handle_to_move_under(handle)
        container = Container(self._root)
        self._containers[handle] = container
        container.mouse_over.connect(self.mouse_over.emit)
        self._splitter.addWidget(container)
        container.grab_window(handle)

class Root(QFrame):
    # Custom moving and sizing detection is needed because moveEvent is fired if
    # the top left of the window moves during resizing.
    moved = Signal()
    resized = Signal()

    enter_size_move = Signal()
    exit_size_move = Signal()

    activation_change = Signal(bool)

    def __init__(self):
        super().__init__()

        self._handles = set()

        self.is_moving = False
        self.is_resizing = False

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
        message = _msg_from_address(int(message))

        # print(hex(message.message))

        if message.message == win32con.WM_ENTERSIZEMOVE:
            self.enter_size_move.emit()
        elif message.message == win32con.WM_EXITSIZEMOVE:
            self.is_moving = False
            self.is_resizing = False
            self.exit_size_move.emit()
        elif message.message == win32con.WM_MOVING:
            self.is_moving = True
            self.moved.emit()
        elif message.message == win32con.WM_SIZING:
            self.is_resizing = True
            self.resized.emit()

        return False

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
