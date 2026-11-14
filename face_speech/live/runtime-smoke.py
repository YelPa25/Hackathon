"""Probe the restrictions from inside the same AppContainer used for model inference."""

import ctypes
from ctypes import wintypes
import socket
import sys
from pathlib import Path


def is_appcontainer():
    token = wintypes.HANDLE()
    if not ctypes.windll.advapi32.OpenProcessToken(ctypes.c_void_p(-1), 8, ctypes.byref(token)):
        raise ctypes.WinError()
    try:
        value = wintypes.DWORD()
        length = wintypes.DWORD()
        if not ctypes.windll.advapi32.GetTokenInformation(
            token, 29, ctypes.byref(value), ctypes.sizeof(value), ctypes.byref(length)
        ):
            raise ctypes.WinError()
        return value.value == 1
    finally:
        ctypes.windll.kernel32.CloseHandle(token)


if __name__ == "__main__":
    if not is_appcontainer():
        raise SystemExit("Expected an AppContainer token")
    for target in sys.argv[1:]:
        try:
            with Path(target).open("rb"):
                pass
        except PermissionError:
            pass
        else:
            raise SystemExit("Access to Core was granted")
        try:
            Path(target).open("r+b").close()
        except PermissionError:
            pass
        else:
            raise SystemExit("Core write access was granted")
    for address in ("127.0.0.1", "1.1.1.1"):
        try:
            with socket.create_connection((address, 8050 if address.startswith("127.") else 443), 2):
                raise SystemExit("Network access was granted")
        except (PermissionError, TimeoutError) as error:
            print(f"{address}: {type(error).__name__}")
    print("AppContainer verified. Core reads and writes were denied. Network probes could not connect.", flush=True)
