import os
import pty
import fcntl
import struct
import signal
import termios
import logging

log = logging.getLogger("terminal")

class TerminalSession:
    def __init__(self, shell="/bin/bash"):
        self.shell = shell
        self.fd = None
        self.pid = None

    def start(self):
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.execve(self.shell, [self.shell], os.environ)
        return self.fd

    def write(self, data):
        if self.fd is not None:
            try:
                os.write(self.fd, data)
            except OSError:
                pass

    def resize(self, rows, cols):
        if self.fd is not None:
            try:
                buf = struct.pack('HHHH', rows, cols, 0, 0)
                fcntl.ioctl(self.fd, termios.TIOCSWINSZ, buf)
            except OSError:
                pass

    def read(self, max_bytes=4096):
        if self.fd is not None:
            try:
                return os.read(self.fd, max_bytes)
            except OSError:
                return b''
        return b''

    def close(self):
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGTERM)
                os.waitpid(self.pid, 0)
            except OSError:
                pass
            self.pid = None
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

    @property
    def is_alive(self):
        if self.pid:
            try:
                pid, status = os.waitpid(self.pid, os.WNOHANG)
                return pid == 0
            except OSError:
                return False
        return False
