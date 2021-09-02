this folder contains modules for data preprocess and
decription analysis.

- extract-inputs: codes for extract inputs from fuzzing
- data: preprocessed numpy format data
- models: trained models
- train: notebooks for training models

- process the data:
    1. copy `afl.db` (generated from `../extract-inputs`) under the folder
    2. run the notebook: `compress.ipynb`
- run the notebook: `inspect-the-data.ipynb`
- run the `/train/train-*` note books to train the data