# import tensorflow as tf
import random

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

import queue

import pprint
from typing import List


import numpy as np

from utils import BITMAP_SIZ, dprint

pp = pprint.PrettyPrinter(indent=2)

def get_model(input_size: int, bitmap_size: int, name: str = None):
    """ create a model """
    SHRINK_FACTOR = 5
    output_size = bitmap_size
    dense_layer_size = output_size // SHRINK_FACTOR
    inputs = keras.Input(shape=(input_size,))
    dense_1 = layers.Dense(dense_layer_size, activation="relu")
    x = dense_1(inputs)
    dense_2 = layers.Dense(dense_layer_size, activation="relu")
    x = dense_2(x)
    dense_3 = layers.Dense(output_size, activation="sigmoid")
    outputs = dense_3(x)
    return keras.Model(inputs=inputs, outputs=outputs, name=name)


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
        self._compress_sample_bitmap()
        self._calc_sample_score()

        if self.model_trained_sample_count < self.MIN_TRAINING_SAMPLES:
            return True

        model_train_score_span = self.model_train_max_score - self.model_train_min_score
        if model_train_score_span <= 0:
            # initially model's max and min score are set to -1 and 1
            return True

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

    # --------------------------- helper functions ------------------------------

    def _clear_samples(self):
        self.samples_X = []
        self.samples_Y = []
        self.samples_Y_compressed = None
        self.samples_score = None

    def _cast_samples(self):
        """ cast samples to ndarray """
        if not isinstance(self.samples_X, list):
            return
        self.samples_X = np.array([np.concatenate((x, np.zeros(self.model_input_size - x.size))) for x in self.samples_X])
        self.samples_Y = np.array(self.samples_Y)

    def _compress_sample_bitmap(self):
        if self.samples_Y_compressed is not None:
            return
        flag = np.greater(self.samples_Y[:, self.edge_selector],
                          0, dtype=np.float32)
        self.samples_Y_compressed = flag
        self.samples_X = tf.keras.preprocessing.sequence.pad_sequences(
            self.samples_X, maxlen=self.model_input_size, dtype=np.float32,
            padding='post'
        )

    def _calc_sample_score(self):
        if self.samples_score is not None:
            return
        self._compress_sample_bitmap()
        self.samples_score = self.calc_score(self.samples_Y_compressed, self.model_edge_score)

    def _update_edge_score(self):
        weight = self.sample_size / (self.edge_score_sample_count + self.sample_size)
        # score = self.sample_edge_score * weight
        np.add(self.edge_score * (1-weight), self.sample_edge_score * weight, out=self.edge_score)
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
                (self.new_observed_edge_index, new_hit_edge_idx)
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

    def print_filter_stat(self):
        print(f"model::{self.model_input_size}->{self.model_output_size}")
        print(f"bitmap_cov_ratio: {self.model_sample_bitmap_coverage}")
        print(f"new_obv_edge_sample_count/tot_sample_num: {self.new_observed_edge_sample_count}/{self.total_sample_count}")
        print(f"oversize-ratio, sample-oversize-ratio:{self.model_oversize_input_ratio}, {self.model_oversize_input_sample_ratio}")
        print(f"oversize-input-count: {self.oversize_input_count}")
        print(f"filter_out: {self.filter_count}")

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
        model = self.model
        return model(inputs, training=False).numpy()

    @staticmethod
    def calc_score(y: np.ndarray, edge_score):
        y = standardize(y)
        return y.dot(edge_score)

    def is_oversize(self, x):
        return x.size > self.model_input_size

    # ============================== main functions =====================================
    def fit_samples(self):
        # cast sample list to ndarray
        self._cast_samples()
        self._update_new_observed_edge_index()
        self._update_sample_count()

        if not self.model or self.need_new_model:
            self.create_new_model()
            dprint("Update/Create new model.")
            dprint(self.model)

        # compress the bitmap according to the current model
        self._compress_sample_bitmap()
        self.print_filter_stat()
        if self.need_fit:
            # _, ncol = self.samples_X.shape
            # if ncol < self.model_input_size:
            #     samples_X = np.pad
            self.model.fit(x=self.samples_X, y=self.samples_Y_compressed, epochs=3)
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
        if self.sample_size >= self.epoch_sample_size:
            dprint("collect a whole batch of samples")
            self.fit_samples()
    
    def filter_one(self, x):

        if not self.model_ready:
            return False 

        if self.is_oversize(x):
            return False  # fuzz the input
        
        x = np.concatenate((x, np.zeros(self.model_input_size-x.size)))
        
        y_hat = self.predict(np.reshape(x, (1, -1)))
        score = self.calc_score(y_hat, self.edge_score)
        # self.write_filter_result(False)  # fuzz the input
        # return
        if score < 0:
            return False  # fuzz the input
            
        roll = random.uniform(0, 1)
        if roll > min(score, 0.95):
            return False  # fuzz the input
        else:
            self.filter_count += 1
            return True   # skip the input
