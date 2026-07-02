"""IME utilities for Windows — bypass Chinese IME interference.

When the Chinese IME is active, pyautogui.write() types through the IME
composition window, producing garbled text instead of the intended input.
Clipboard paste (Ctrl+V) completely bypasses the IME pipeline.
"""
import time

import pyautogui
import pyperclip


def type_unicode(text: str, interval: float = 0.05):
    """Type text via clipboard paste (Ctrl+V), bypassing IME entirely."""
    pyperclip.copy(text)
    time.sleep(0.05)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(interval)
