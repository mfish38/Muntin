
from PySide2.QtCore import (
    QTimer,
    QPoint,
    QRect,
)

import win32gui
import win32con

class WindowMonitor:
    '''
    Polls desktop windows and triggers events on widgets that register for them.
    '''
    def __init__(self):
        self._timer = QTimer()
        self._timer.timeout.connect(self._timeout)
        self._timer.start(200)
        self._rectangles = []
        self._z_positions = {}
        self._widgets = []
        self._previous_overlaps = []
        self._previous_rectangles = {}

    def register(self, widget):
        self._widgets.append(widget)
        self._previous_overlaps.append(set())

    def _check_for_overlap_changes(self):
        previous_overlaps = self._previous_overlaps
        previous_rectangles = self._previous_rectangles

        for widget_index, widget in enumerate(self._widgets):
            position = widget.mapToGlobal(QPoint(0,0))
            rectangle = QRect(position, widget.size())

            # Test windows above the window containing the widget
            current_overlaps = set()
            window_handle = widget.window().effectiveWinId()
            window_z = self._z_positions[window_handle]
            for test_handle, test_rectangle in self._rectangles[:window_z]:
                if not rectangle.intersects(test_rectangle):
                    continue

                current_overlaps.add(test_handle)

                if test_handle not in previous_overlaps[widget_index]:
                    widget.overlap_enter_event(test_handle, test_rectangle)
                    previous_rectangles[test_handle] = test_rectangle
                    continue

                if test_rectangle != previous_rectangles[test_handle]:
                    widget.overlap_move_event(test_handle, test_rectangle)
                    previous_rectangles[test_handle] = test_rectangle
                    continue

            for overlap_handle in previous_overlaps[widget_index] - current_overlaps:
                last_location = previous_rectangles.pop(overlap_handle)
                widget.overlap_exit_event(overlap_handle, last_location)

            previous_overlaps[widget_index] = current_overlaps

    def _scan_windows(self):
        def window_selector(handle, argument):
            # styles = win32gui.GetWindowLong(handle, win32con.GWL_STYLE)
            extended_styles = win32gui.GetWindowLong(handle, win32con.GWL_EXSTYLE)

            if extended_styles & win32con.WS_EX_TOOLWINDOW:
                return

            rectangles, z_positions = argument
            left, top, right, bottom = win32gui.GetWindowRect(handle)
            rectangles.append(
                (
                    handle,
                    QRect(left, top, right - left, bottom - top)
                )
            )
            z_positions[handle] = len(z_positions)

        rectangles = []
        z_positions = {}
        win32gui.EnumWindows(window_selector, (rectangles, z_positions))
        self._rectangles = rectangles
        self._z_positions = z_positions

    def _timeout(self):
        self._scan_windows()
        self._check_for_overlap_changes()
