
import ctypes
import ctypes.wintypes
import sys

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QApplication,
    QFrame,
)

from PySide2.QtGui import (
    QWindow,
    QPainter
)

from window_capture import capture_window

user32 = ctypes.windll.user32

class Container(QFrame):
    def __init__(self):
        super().__init__()

        self._handle = None
        self._sync_enabled = True
        self._border = 5
        self._top_border = 32
        self._image = None

    def grab_window(self, window_handle):
        self._handle = window_handle

    def _sync_window(self):
        if not self._sync_enabled:
            return

        top_border = self._top_border
        border = self._border
        twice_border = border * 2
        size = self.size()
        pos = self.pos()

        SWP_ASYNCWINDOWPOS = 0x4000 
        user32.SetWindowPos(
            self._handle,
            self.effectiveWinId(),
            pos.x() + border,
            pos.y() + top_border,
            size.width() - twice_border,
            size.height() - border,
            SWP_ASYNCWINDOWPOS
        )

    def paintEvent(self, event):
        if self._image is None:
            return

        # TODO: performance here seems quite bade, causes window under to lag during moves, either hide the window or make this faster
        painter = QPainter(self)
        painter.drawImage(4, 1, self._image)

    def resizeEvent(self, event):
        self._image = capture_window(self._handle)
        self._sync_window()

    def moveEvent(self, event):
        self._sync_window()

    def _enter_size_move(self):
        self._sync_enabled = True

    def _move_to_front(self):
        self._sync_enabled = False

        top_border = self._top_border
        border = self._border
        twice_border = border * 2
        size = self.size()
        pos = self.pos()

        SWP_ASYNCWINDOWPOS = 0x4000 
        user32.SetWindowPos(
            self.effectiveWinId(),
            self._handle,
            pos.x() - border - 2,
            pos.y(),
            size.width() + twice_border + 6,
            size.height() + top_border + border + 2,
            SWP_ASYNCWINDOWPOS
        )

    def _exit_size_move(self):
        self._move_to_front()

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
            self._enter_size_move()
        elif message.message == WM_EXITSIZEMOVE:
            self._exit_size_move()

        return False
    
handle = user32.FindWindowW(u'Notepad', None)

app = QApplication(sys.argv)
window = Container()
window.grab_window(handle)
window.show()
app.exec_()
