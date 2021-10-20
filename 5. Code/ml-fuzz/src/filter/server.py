import socket
import socketserver
import queue
from typing import List, Tuple
import numpy as np
import threading

from filter.utils import ENDIAN, BITMAP_SIZ, INPUT_SIZ_LEN, dprint
from filter.filter import Filter


class IOMixin:
    request: socket  # inherited from socketserver as a mixin

    FILTER_MODE = 1
    SAMPLE_MODE = 2
    FINISH_MODE = 0

    def _read_int(self, nbytes: int) -> int:
        """ read `nbytes` as an integer """
        n = nbytes
        data = self.request.recv(n)  # type of self.request is `Socket`
        if n != len(data):
            raise IOError("fail reading int")
        raw = b"".join(data)
        size = int.from_bytes(raw, ENDIAN, signed=False)
        return size

    def read_mode(self):
        mode = self._read_int(1)
        return mode

    def _read_bytes(self, size) -> bytes:
        n = size
        raw = []
        while n:
            data = self.request.recv(n)
            raw.append(data)
            n -= len(data)
        return b"".join(raw)

    def _read_ndarray(self, size, dtype) -> np.ndarray:
        return np.frombuffer(self._read_bytes(size), dtype=dtype)

    # def read_buffer_size(self) -> int:
    #     return self._read_int(BUFFER_SIZ_LEN)

    def read_input_size(self) -> int:
        return self._read_int(INPUT_SIZ_LEN)

    def read_bitmap(self) -> np.ndarray:
        return self._read_ndarray(BITMAP_SIZ, np.uint8)

    def read_raw_bitmap(self) -> bytes:
        return self._read_bytes(BITMAP_SIZ)

    def read_raw_input(self) -> bytes:
        input_size = self.read_input_size()
        return self._read_bytes(input_size)

    def read_input(self) -> np.ndarray:
        input_size = self.read_input_size()
        data = self._read_ndarray(input_size, np.byte)
        return data

    def read_sample(self) -> Tuple[np.ndarray, np.ndarray]:
        x = self.read_input()
        y = self.read_bitmap()
        return x, y

    def write_filter_result(self, filter_out: bool):
        data = b'\x01' if filter_out else b'\x00'
        self.request.send(data)
        # print("result-done")
    
    def write_input(self, data: bytes):
        """ send input back to fuzzer """
        self.request.send(int.to_bytes(len(data), byteorder=ENDIAN, length=32, signed=False))
        self.request.send(data)


class FilterThread(threading.Thread):

    def __init__(self, filter: Filter, in_queue: queue.Queue, io: IOMixin):
        super().__init__()
        self.filter = filter
        self.queue = in_queue
        self.io = io

    def run(self):
        x_lst: List[bytes] = []
        batch_size = 1000
        while 1:
            raw_x: bytes = self.queue.get()
            if raw_x is None:
                self.queue.task_done()
                break
            x_lst.append(raw_x)
            if len(x_lst) >= batch_size:
                xs = self.filter.filter(x_lst)
                for x in xs:
                    self.io.write_input(x)
            self.queue.task_done()


class FeedbackSampleThread(threading.Thread):

    def __init__(self, filter: Filter, q: queue.Queue):
        super().__init__()
        self.filter = filter
        self.queue = q
    
    def run(self):
        while 1:
            item = self.queue.get()
            if item is None:
                self.queue.task_done()
                break
            x, y = item
            self.filter.observe(x, y)
            self.queue.task_done()


class Handler(socketserver.BaseRequestHandler, IOMixin):

    def handle(self):
        dprint("fuzzer connected")
        self.filter_queue = queue.Queue(maxsize=2000)
        self.sample_queue = queue.Queue(100)
        filter = Filter()
        self.filterThread = FilterThread(filter, self.filter_queue, self)
        self.sampleThread = FeedbackSampleThread(filter, self.sample_queue)
        self.filterThread.run()
        self.sampleThread.run()

        # seen_sample, seen_test = False, False
        while True:
            mode = self.read_mode()
            if mode == self.SAMPLE_MODE:
                x, y = self.read_sample()
                self.sample_queue.put((x, y))
            elif mode == self.FILTER_MODE:
                raw_x = self.read_raw_input()
                self.filter_queue.put(raw_x)
            elif mode == self.FINISH_MODE:
                break
    
    def finish(self) -> None:
        super().finish()
        self.filter_queue.put(None)
        self.sample_queue.put(None)
        self.filterThread.join()
        self.sampleThread.join()

        
if __name__ == "__main__":
    SOCK = "/tmp/afl-mlfilter.sock"
    import os
    if os.path.exists(SOCK):
        os.remove(SOCK)
    with socketserver.UnixStreamServer(SOCK, Handler) as server:
        server.serve_forever()
