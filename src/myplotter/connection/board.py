import serial
from serial.tools import list_ports


USB_VID = 0x04D8
USB_PID = 0xFD92


def discover_boards():
    return [port.device for port in list_ports.comports()
            if port.vid == USB_VID and port.pid == USB_PID]


class Board:
    def __init__(self):
        self.port = None

    @property
    def connected(self):
        return self.port is not None and self.port.is_open

    def connect(self, name):
        self.disconnect()
        port = serial.Serial(name, timeout=1, write_timeout=1)
        try:
            port.reset_input_buffer()
            port.write(b"V\r")
            version = port.readline().decode("ascii", errors="replace").strip()
            if not version.startswith("EBB"):
                raise RuntimeError(f"No EiBotBoard response on {name}")
        except Exception:
            port.close()
            raise
        self.port = port
        return version

    def disconnect(self):
        if self.port is not None:
            self.port.close()
            self.port = None

    def command(self, value):
        if not self.connected:
            raise RuntimeError("Connect to the plotter first")
        self.port.write((value + "\r").encode("ascii"))
        response = self.port.readline().decode("ascii", errors="replace").strip()
        if response != "OK":
            raise RuntimeError(response or "Board did not acknowledge the command")
