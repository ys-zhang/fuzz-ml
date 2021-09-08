# import tensorflow as tf
import random

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

import sys
from socket import socket
import socketserver
from typing import List, Tuple


import numpy as np


BITMAP_SIZ = 1 << 16  # 64k bitmap
# BUFFER_SIZ_LEN = 32
ENDIAN = sys.byteorder
INPUT_SIZ_LEN = 4  # length of the current input


def get_model(input_size: int, bitmap_size: int, name: str = None):
    """ create a model """
    SHRINK_FACTOR = 3
    output_size = bitmap_size
    dense_layer_size = output_size // SHRINK_FACTOR
    inputs = keras.Input(shape=(input_size,))
    dense_1 = layers.Dense(dense_layer_size, activation="relu")
    x = dense_1(inputs)
    dense_2 = layers.Dense(dense_layer_size, activation="relu")
    x = dense_2(x)
    dense_3 = layers.Dense(output_size, activation="sigmoid")
    outputs = dense_3(x)
    return keras.Model(inputs=input, outputs=outputs, name=name)


def compile_model(model: keras.Model):
    loss = "binary_crossentropy"
    metrics = ["binary_accuracy", keras.metrics.Recall(thresholds=0.5)]
    opt = keras.optimizers.Adam(learning_rate=0.0001)
    model.compile(optimizer=opt, loss=loss, metrics=metrics)


def standardize(mat: np.ndarray) -> np.ndarray:
    if mat.ndim == 2:
        centered = mat - mat.mean(axis=1, keepdims=True)
        std = np.linalg.norm(centered, axis=1, keepdims=True)
        return centered / std
    elif mat.ndim == 1:
        mat = mat - mat.mean()
        return mat / np.linalg.norm(mat)
    else:
        raise NotImplementedError("too many dimensions")


def dprint(obj):
    """ debug print """
    print(obj)


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
        dprint(mode)
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
        # dprint(input_size)
        return self._read_ndarray(input_size, np.byte)

    def read_sample(self) -> Tuple[np.ndarray, np.ndarray]:
        input_ = self.read_input()
        bitmap = self.read_bitmap()
        return input_, bitmap

    def write_filter_result(self, filter_out: bool):
        data = b'\x01' if filter_out else b'\x00'
        self.request.send(data)


class Filter:

    MODE_FILTER = 0
    MODE_TRAIN = 1

    REGULAR_EPOCH_SIZE = 200
    INITIAL_EPOCH_SIZE = 20_000
    INITIAL_MODEL_INPUT_SIZE = 512
    MIN_TRAINING_SAMPLES = INITIAL_EPOCH_SIZE

    def __init__(self):

        # a batch of samples
        self.samples_X = []
        self.samples_Y = []
        self.samples_Y_compressed = None
        self.samples_score = None

        # edge statistics
        self.edge_selector = np.array([], dtype=np.uint16)   # type: np.ndarray
        self.new_observed_edge_index = np.array([], dtype=np.uint16)  # type: np.ndarray
        self.new_observed_edge_sample_count = 0
        self.total_sample_count = 0
        # virgin flag covers all edges in edge_selector
        # or new_observed_edge_index
        self.virgin_flag = np.ones((BITMAP_SIZ,), dtype=bool)

        # score
        self.edge_score = 0
        # num-of-samples contrib to edge score
        self.edge_score_sample_count = 0

        # model
        self.model_input_size = self.INITIAL_MODEL_INPUT_SIZE
        self.model_output_size = 0
        self.oversize_input_count = 0
        self.longest_input_size = self.model_input_size
        self._models = []            # type: List[keras.Model]
        self.model_edge_score = 0    # edge score of the training set
        self.model_train_min_score = 1
        self.model_train_max_score = -1
        self.model_trained_sample_count = 0  # num of samples used in training

        # running statistics
        self.filter_count = 0

    @property
    def model(self) -> keras.Model:
        """ the current model """
        if not self._models:
            return None
        return self._models[-1]

    @property
    def model_ready(self) -> bool:
        return self.model_trained_sample_count >= self.INITIAL_EPOCH_SIZE

    @property
    def sample_size(self) -> int:
        return len(self.samples_Y)

    @property
    def epoch_sample_size(self) -> int:
        """ number of samples needed to try refitting the model """
        if self.model_trained_sample_count == 0:
            # initially we first collect more sample to train
            return self.INITIAL_EPOCH_SIZE
        return self.REGULAR_EPOCH_SIZE

    @property
    def need_new_model(self) -> bool:
        """
        whether we need to retrain the model base on current observations
        """
        # whether the model_input_size is appropriate
        if self.model_oversize_input_sample_ratio > 0.1:
            return True
        if self.model_oversize_input_ratio > 0.1:
            return True
        # whether the model_output_size is appropriate
        if self.model_edge_coverage < 0.9:
            return True
        if self.model_sample_bitmap_coverage < 0.9:
            return True
        return False

    @property
    def need_fit(self) -> bool:
        """
        whether we need to fit the model against the observed sample
        """
        if self.model_trained_sample_count < self.MIN_TRAINING_SAMPLES:
            return True

        model_train_score_span = self.model_train_max_score - self.model_train_min_score
        if model_train_score_span <= 0:
            # initially model's max and min score are set to -1 and 1
            return True

        self._compress_sample_bitmap()
        self._calc_sample_score()
        avg_score = np.mean(self.samples_score)
        # if avg_score < self.model_train_min_score + model_train_score_span * 0.2:
        #     return True
        if avg_score < self.model_train_max_score - model_train_score_span * 0.2:
            return True

        return False

    # ------ parameters for deciding whether to retrain the model -------

    @property
    def has_uncovered_edge(self):
        """
        whether there are hit edge not covered by current model

        this is a parameter for deciding whether to retrain the model.
        """
        return self.new_observed_edge_index.size > 0

    @property
    def model_edge_coverage(self) -> float:
        """
        percentage of hit edges that are covered by the current model.

        this is a parameter for deciding whether to retrain the model.
        """
        covered = self.edge_selector.size
        uncovered = self.new_observed_edge_index.size
        return covered / (covered + uncovered)

    @property
    def model_sample_bitmap_coverage(self) -> float:
        """
        percentage of samples whose bitmap are fully covered
        by the current model.

        this is a parameter for deciding whether to retrain the model.
        """
        return 1 - self.new_observed_edge_sample_count / self.total_sample_count

    @property
    def model_oversize_input_sample_ratio(self):
        total = self.oversize_input_count + self.total_sample_count
        return self.oversize_input_count / total

    @property
    def model_oversize_input_ratio(self):
        return self.longest_input_size / self.model_input_size - 1

    @property
    def sample_edge_score(self):
        """ normalized edge score of the sample bitmaps """
        score_sum = standardize(self.samples_Y_compressed).sum(0)
        return score_sum / np.linalg.norm(score_sum)

    @property
    def sample_edge_score_deviation(self):
        """ deviation of sample edge score and model edge score
        """
        return self.sample_edge_score.dot(self.model_edge_score)

    def create_new_model(self) -> keras.Model:
        model_version = len(self._models) + 1
        self._update_model_params()
        model = get_model(
            self.model_input_size,
            self.model_output_size,
            f"filter-ver-{model_version}",
        )
        compile_model(model)
        self._models.append(model)
        return model

    def predict(self, inputs: np.ndarray) -> np.ndarray:
        return self.model.predict(inputs)

    @staticmethod
    def calc_score(y: np.ndarray, edge_score):
        y = standardize(y)
        return y.dot(edge_score)

    def is_oversize(self, x):
        return x.size > self.model_input_size

    def fit_samples(self):
        # cast sample list to ndarray
        self._cast_samples()
        self._update_new_observed_edge_index()

        if not self.model or self.need_new_model:
            self.create_new_model()
            dprint(self.model)

        # compress the bitmap according to the current model
        self._compress_sample_bitmap()
        if self.need_fit:
            self.model.fit(x=self.samples_X, y=self.samples_Y_compressed, epochs=5)
            self.model_trained_sample_count += self.sample_size
            self.model_train_max_score = max(self.model_train_max_score, np.max(self.samples_score))
            self.model_train_min_score = min(self.model_train_min_score, np.min(self.samples_score))

        # maintain edge statistics
        # even not fit we update the edge_score i.e. weight
        self._update_edge_score()
        self._clear_samples()

    def observe(self, x: np.ndarray, y: np.ndarray):
        # observed an oversize input, throw away
        if x.size > self.model_input_size:
            # maintain model statistics
            self.oversize_input_count += 1
            self.longest_input_size = max(self.longest_input_size, x.size)
            # since this sample is dropped, we check whether it hits uncovered edges
            if np.any(np.delete(y, self.edge_selector)):
                self.new_observed_edge_sample_count += 1
            # maintain edge statistics
            self.total_sample_count += 1
            # TODO: update edge score here
            return

        self.samples_X.append(x)
        self.samples_Y.append(y)
        dprint("observe")
        if self.sample_size >= self.epoch_sample_size:
            self.fit_samples()

    # --------------------------- helper functions ------------------------------

    def _clear_samples(self):
        self.samples_X = []
        self.samples_Y = []
        self.samples_Y_compressed = None
        self.samples_score = None

    def _cast_samples(self):
        """ cast samples to ndarray """
        if not isinstance(self.samples_X, np.ndarray):
            self.samples_X = np.array(self.samples_X)
            self.samples_Y = np.array(self.samples_Y)

    def _compress_sample_bitmap(self):
        if self.samples_Y_compressed is not None:
            return
        flag = np.greater(self.samples_Y[:, self.edge_selector],
                          0, dtype=np.float32)
        self.samples_Y_compressed = flag

    def _calc_sample_score(self):
        if self.samples_score is not None:
            return
        self._compress_sample_bitmap()
        self.samples_score = self.calc_score(self.samples_Y_compressed, self.model_edge_score)

    def _update_edge_score(self):
        weight = self.sample_size / self.edge_score_sample_count
        score = self.sample_edge_score * weight
        np.add(self.edge_score, score, out=self.edge_score)
        np.divide(self.edge_score, np.linalg.norm(self.edge_score), out=self.edge_score)
        self.edge_score_sample_count += self.sample_size

    def _update_new_observed_edge_index(self):
        """
        check whether there are new hit edge
            in the current sample batch
        """
        hit = np.any(self.samples_Y, axis=0)
        # filter out edges that already seen
        np.logical_and(hit, self.virgin_flag, out=hit)
        (new_hit_edge_idx,) = np.nonzero(hit)
        new_hit_edge_idx = new_hit_edge_idx.astype(np.uint16)

        # if we observe some new edges are hit
        if new_hit_edge_idx.size > 0:
            # update virgin edge flag
            np.logical_xor(hit, self.virgin_flag, out=self.virgin_flag)
            # update new_observed_edge_index
            self.new_observed_edge_index = np.concatenate(
                self.new_observed_edge_index, new_hit_edge_idx
            )

        return new_hit_edge_idx

    def _update_sample_count(self):
        # update sample count
        self.total_sample_count += self.sample_size
        if not self.has_uncovered_edge:
            self.new_observed_edge_sample_count += np.any(
                self.samples_Y[:, self.new_observed_edge_index], axis=1
            ).sum()

    def _update_edge_selector(self):
        # retain the order of the model response
        #   i.e. we may able to reuse weights from previous model
        self.edge_selector = np.concatenate(
            [self.edge_selector, self.new_observed_edge_index]
        )
        self.new_observed_edge_index = np.array([], dtype=np.uint16)
        self.new_observed_edge_sample_count = 0
    
    def _update_model_params(self):
        self.model_input_size = self.longest_input_size
        self.oversize_input_count = 0
        self._update_edge_selector()
        self.model_output_size = self.edge_selector.size
        self.model_edge_score = np.zeros((self.model_output_size,), dtype=np.float32)
        self.model_trained_sample_count = 0
        self.model_train_min_score = 1
        self.model_train_max_score = -1

        # reset edge score
        self.edge_score = np.zeros_like(self.model_edge_score)
        self.edge_score_sample_count = 0


class Handler(socketserver.BaseRequestHandler, IOMixin, Filter):

    def handle(self):
        dprint("fuzzer connected")
        Filter.__init__(self)
        seen_sample, seen_test = False, False
        while True:
            is_sample = self.read_mode()
            if is_sample:
                if not seen_sample:
                    dprint("read sample")
                    seen_sample = True
                input_, bitmap = self.read_sample()
                self.observe(input_, bitmap)
            else:
                if not seen_test:
                    dprint("read test")
                    seen_test = True
                # do a filter
                self.filter_one()

    def filter_one(self):
        if not self.model_ready:
            _ = self.read_input()            # discard input
            self.write_filter_result(False)  # fuzz the input
            return

        x = self.read_input()
        if self.is_oversize(x):
            self.write_filter_result(False)  # fuzz the input
            return
        y_hat = self.predict(x)
        score = self.calc_score(y_hat, self.edge_score)
        if score < 0:
            self.write_filter_result(False)  # fuzz the input
            return
        roll = random.uniform(0, 1)
        if roll > min(score, 0.95):
            self.write_filter_result(False)  # fuzz the input
        else:
            dprint("filter out 1")
            self.filter_count += 1
            if self.filter_count % 10000 == 0:
                dprint(f"filtered {self.filter_count} samples")
            self.write_filter_result(True)   # skip the input


if __name__ == "__main__":
    SOCK = "/tmp/afl-mlfilter.sock"
    with socketserver.UnixStreamServer(SOCK, Handler) as server:
        server.serve_forever()
