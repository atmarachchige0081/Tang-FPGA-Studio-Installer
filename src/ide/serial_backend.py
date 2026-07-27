"""Dependency-free Windows serial backend and UART presentation helpers."""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import os
import re
import threading
from typing import Callable


@dataclass(frozen=True)
class SerialPortInfo:
    port: str
    description: str


def list_serial_ports() -> list[SerialPortInfo]:
    """List Windows COM ports from the registry without requiring pyserial."""
    if os.name != "nt":
        return []
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
    except OSError:
        return []
    values: list[SerialPortInfo] = []
    with key:
        index = 0
        while True:
            try:
                device, port, _kind = winreg.EnumValue(key, index)
            except OSError:
                break
            values.append(SerialPortInfo(str(port).upper(), str(device).replace("\\Device\\", "")))
            index += 1
    return sorted(values, key=lambda item: natural_port_key(item.port))


def natural_port_key(value: str) -> tuple[str, int]:
    match = re.fullmatch(r"([A-Za-z]+)(\d+)", value.strip())
    return (match.group(1).upper(), int(match.group(2))) if match else (value.upper(), -1)


def preferred_serial_port(ports: list[SerialPortInfo]) -> SerialPortInfo | None:
    """Prefer a USB/VCP UART and never auto-select a Bluetooth modem."""
    if len(ports) == 1:
        return ports[0]
    candidates = [
        item for item in ports
        if not any(marker in item.description.lower() for marker in ("bth", "bluetooth", "modem"))
    ]
    return candidates[-1] if candidates else None


def encode_terminal_input(value: str, mode: str) -> bytes:
    if mode == "hex":
        compact = re.sub(r"[\s,_-]+", "", value)
        if not compact:
            return b""
        if len(compact) % 2 or not re.fullmatch(r"[0-9a-fA-F]+", compact):
            raise ValueError("Hex input needs complete byte pairs, for example: 48 65 6C 6C 6F")
        return bytes.fromhex(compact)
    return value.encode("utf-8")


def format_terminal_bytes(value: bytes, mode: str) -> str:
    if mode == "hex":
        return " ".join(f"{byte:02X}" for byte in value)
    return value.decode("utf-8", errors="replace")


class SerialConnection:
    """Small 8-N-1 Win32 serial connection with non-blocking background reads."""

    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    def __init__(self, port: str, baud: int, on_bytes: Callable[[bytes], None]):
        self.port = port.upper()
        self.baud = baud
        self.on_bytes = on_bytes
        self.handle: int | None = None
        self._stop = threading.Event()
        self._reader: threading.Thread | None = None

    @property
    def is_open(self) -> bool:
        return self.handle not in {None, self.INVALID_HANDLE_VALUE}

    def open(self) -> None:
        if os.name != "nt":
            raise OSError("The integrated UART terminal currently supports Windows COM ports.")
        if self.is_open:
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = (
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        )
        kernel32.CreateFileW.restype = wintypes.HANDLE
        path = rf"\\.\{self.port}"
        handle = kernel32.CreateFileW(
            path, 0xC0000000, 0, None, 3, 0, None,
        )
        if handle == self.INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        self.handle = handle
        try:
            self._configure(kernel32)
        except Exception:
            kernel32.CloseHandle(handle)
            self.handle = None
            raise
        self._stop.clear()
        self._reader = threading.Thread(target=self._read_loop, daemon=True, name="uart-reader")
        self._reader.start()

    def _configure(self, kernel32) -> None:
        class DCB(ctypes.Structure):
            _fields_ = [
                ("DCBlength", wintypes.DWORD), ("BaudRate", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("wReserved", wintypes.WORD),
                ("XonLim", wintypes.WORD), ("XoffLim", wintypes.WORD),
                ("ByteSize", wintypes.BYTE), ("Parity", wintypes.BYTE),
                ("StopBits", wintypes.BYTE), ("XonChar", ctypes.c_char),
                ("XoffChar", ctypes.c_char), ("ErrorChar", ctypes.c_char),
                ("EofChar", ctypes.c_char), ("EvtChar", ctypes.c_char),
                ("wReserved1", wintypes.WORD),
            ]

        class COMMTIMEOUTS(ctypes.Structure):
            _fields_ = [
                ("ReadIntervalTimeout", wintypes.DWORD),
                ("ReadTotalTimeoutMultiplier", wintypes.DWORD),
                ("ReadTotalTimeoutConstant", wintypes.DWORD),
                ("WriteTotalTimeoutMultiplier", wintypes.DWORD),
                ("WriteTotalTimeoutConstant", wintypes.DWORD),
            ]

        dcb = DCB()
        dcb.DCBlength = ctypes.sizeof(DCB)
        if not kernel32.GetCommState(self.handle, ctypes.byref(dcb)):
            raise ctypes.WinError(ctypes.get_last_error())
        dcb.BaudRate = self.baud
        dcb.flags = 1  # fBinary; software/hardware flow control disabled.
        dcb.ByteSize = 8
        dcb.Parity = 0
        dcb.StopBits = 0
        if not kernel32.SetCommState(self.handle, ctypes.byref(dcb)):
            raise ctypes.WinError(ctypes.get_last_error())
        timeouts = COMMTIMEOUTS(50, 0, 50, 0, 1000)
        if not kernel32.SetCommTimeouts(self.handle, ctypes.byref(timeouts)):
            raise ctypes.WinError(ctypes.get_last_error())

    def _read_loop(self) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        while not self._stop.is_set() and self.is_open:
            buffer = ctypes.create_string_buffer(4096)
            received = wintypes.DWORD()
            ok = kernel32.ReadFile(self.handle, buffer, len(buffer), ctypes.byref(received), None)
            if not ok:
                if not self._stop.is_set():
                    self.on_bytes(b"")
                return
            if received.value:
                self.on_bytes(buffer.raw[:received.value])

    def write(self, value: bytes) -> None:
        if not self.is_open:
            raise OSError("The serial port is not connected.")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        written = wintypes.DWORD()
        buffer = ctypes.create_string_buffer(value)
        if not kernel32.WriteFile(self.handle, buffer, len(value), ctypes.byref(written), None):
            raise ctypes.WinError(ctypes.get_last_error())
        if written.value != len(value):
            raise OSError(f"Only {written.value} of {len(value)} serial bytes were written.")

    def close(self) -> None:
        self._stop.set()
        if self.is_open:
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self.handle)
        self.handle = None
        reader = self._reader
        if reader and reader is not threading.current_thread():
            reader.join(timeout=0.4)
        self._reader = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, _kind, _value, _traceback):
        self.close()
