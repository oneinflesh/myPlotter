import serial
import time
from serial.tools import list_ports


USB_VID = 0x04D8
USB_PID = 0xFD92


def _read_line(port):
    for _ in range(3):
        line = port.readline().decode("ascii", errors="replace").strip()
        if line:
            return line
    return ""


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
            version = _read_line(port)
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
        response = _read_line(self.port)
        if response != "OK":
            raise RuntimeError(response or "Board did not acknowledge the command")

    def wait_idle(self, stop_requested=None, on_poll=None):
        if not self.connected:
            raise RuntimeError("Plotter disconnected")
        while True:
            active, queued = self.motion_status()
            if on_poll is not None:
                on_poll()
            if not active and not queued:
                return
            if stop_requested is not None and stop_requested():
                self.stop_motion()
                return
            time.sleep(0.04)

    def motion_status(self):
        if not self.connected:
            raise RuntimeError("Plotter disconnected")
        self.port.write(b"QM\r")
        response = _read_line(self.port)
        parts = response.split(",")
        if len(parts) != 5 or parts[0] != "QM":
            raise RuntimeError(f"Unexpected motor status: {response or 'no response'}")
        try:
            values = [int(value) for value in parts[1:]]
        except ValueError as error:
            raise RuntimeError(f"Unexpected motor status: {response}") from error
        return values[0] != 0, values[3] != 0

    def stop_motion(self):
        if not self.connected:
            return
        self.port.write(b"ES\r")
        for _ in range(2):
            response = _read_line(self.port)
            if response == "OK":
                return
        raise RuntimeError("Board did not acknowledge stop")

    def query_steps(self):
        if not self.connected:
            raise RuntimeError("Plotter disconnected")
        self.port.write(b"QS\r")
        response = _read_line(self.port)
        acknowledgement = _read_line(self.port)
        try:
            first, second = (int(value) for value in response.split(","))
        except ValueError as error:
            raise RuntimeError(f"Unexpected position response: {response}") from error
        if acknowledgement != "OK":
            raise RuntimeError("Board did not acknowledge position query")
        return first, second
