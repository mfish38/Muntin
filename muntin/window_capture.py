import win32gui
import win32ui
from ctypes import windll
from io import BytesIO
from PIL import Image

from PySide2.QtGui import QImage

# TODO: can dcs be reused, in which case a class for tracking a window might be faster

def capture_window(window_handle):
    # https://stackoverflow.com/a/24352388

    # Change the line below depending on whether you want the whole window
    # or just the client area.
    #left, top, right, bot = win32gui.GetClientRect(window_handle)
    left, top, right, bot = win32gui.GetWindowRect(window_handle)
    w = right - left
    h = bot - top

    hwndDC = win32gui.GetWindowDC(window_handle)
    mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()

    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)

    saveDC.SelectObject(saveBitMap)

    PW_RENDERFULLCONTENT = 2
    result = windll.user32.PrintWindow(window_handle, saveDC.GetSafeHdc(), PW_RENDERFULLCONTENT) 
    # print(result)

    bmpinfo = saveBitMap.GetInfo()
    bmpstr = saveBitMap.GetBitmapBits(True)

    im = Image.frombuffer(
        'RGB',
        (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
        bmpstr, 'raw', 'BGRX', 0, 1)

    buffer = BytesIO()
    im.save(buffer, 'BMP')

    qimage = QImage()
    qimage.loadFromData(buffer.getvalue(), 'BMP')

    return qimage

    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)

    # if result == 1:
    #     #PrintWindow Succeeded
    #     im.save("test.png")
