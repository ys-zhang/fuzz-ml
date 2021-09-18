import socket
import socketserver
from typing import Tuple
import numpy as np

from utils import ENDIAN, BITMAP_SIZ, INPUT_SIZ_LEN, dprint
from filter import Filter

class IOMixin:
    request: socket  # inherited from socketserver as a mixin

    def _read_int(self, nbytes: int) -> int:
        """ read `nbytes` as an integer """
        n = nbytes
        rst = []
        while n:
            data = self.request.recv(n)  # type of self.request is `Socket`
            n -= len(data)
            rst.append(data)
        raw = b"".join(rst)
        size = int.from_bytes(raw, ENDIAN, signed=False)
        return size

    def read_mode(self):
        mode = self._read_int(1)
        return mode

    def is_sample(self):
        return self.read_mode() != 0

    def _read_ndarray(self, size, dtype) -> np.ndarray:
        n = size
        bitmap = []
        while n:
            data = self.request.recv(n)
            bitmap.append(data)
            n -= len(data)
        return np.frombuffer(b"".join(bitmap), dtype=dtype)

    # def read_buffer_size(self) -> int:
    #     return self._read_int(BUFFER_SIZ_LEN)

    def read_input_size(self) -> int:
        return self._read_int(INPUT_SIZ_LEN)

    def read_bitmap(self) -> np.ndarray:
        return self._read_ndarray(BITMAP_SIZ, np.uint8)

    def read_input(self) -> np.ndarray:
        input_size = self.read_input_size()
        data = self._read_ndarray(input_size, np.byte)
        return data

    def read_sample(self) -> Tuple[np.ndarray, np.ndarray]:
        input_ = self.read_input()
        bitmap = self.read_bitmap()
        return input_, bitmap

    def write_filter_result(self, filter_out: bool):
        data = b'\x01' if filter_out else b'\x00'
        self.request.send(data)
        # print("result-done")



class Handler(socketserver.BaseRequestHandler, IOMixin, Filter):

    def handle(self):
        dprint("fuzzer connected")
        Filter.__init__(self)
        # seen_sample, seen_test = False, False
        while True:
            if self.is_sample():
                input_, bitmap = self.read_sample()
                self.observe(input_, bitmap)
            else:
                x = self.read_input()
                self.write_filter_result(self.filter_one(x))
        

if __name__ == "__main__":
    SOCK = "/tmp/afl-mlfilter.sock"
    import os
    if os.path.exists(SOCK):
        os.remove(SOCK)
    with socketserver.UnixStreamServer(SOCK, Handler) as server:
        server.serve_forever()