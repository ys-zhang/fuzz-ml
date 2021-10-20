PREFIX     ?= /usr/local
BIN_PATH    = $(PREFIX)/bin
HELPER_PATH = $(PREFIX)/lib/afl
DOC_PATH    = $(PREFIX)/share/doc/afl
MISC_PATH   = $(PREFIX)/share/afl

SRC_DIR     = src
# PROGS intentionally omit afl-as, which gets installed elsewhere.

IDIR       = $(SRC_DIR)/afl
CFLAGS     ?= -O2 -funroll-loops
CFLAGS     += -Wall -D_FORTIFY_SOURCE=2 -g -Wno-pointer-sign \
	      -DAFL_PATH=\"$(HELPER_PATH)\" -DDOC_PATH=\"$(DOC_PATH)\" \
	      -DBIN_PATH=\"$(BIN_PATH)\"
CFLAGS     += -DAFL_LIB           # compile afl as a lib
CFLAGS     += -I$(IDIR)
LDFLAGS    += -ldl

AFL_COMM_HDR = alloc-inl.h config.h debug.h types.h mlfilter.h chan.c
AFL_FUZZ_SRC = afl-fuzz.c

AFL_FUZZ_SRC = $(addprefix, $(SRC_DIR)/, AFL_FUZZ_SRC)


CYTHON_FILES = mlfuzz.pyx
CYTHON_FILES = $(addprefix, $(SRC_DIR)/, CYTHON_FILES)
FILTER_FILES = filter.py utils.py
CYTHON_FILES = $(addprefix, $(SRC_DIR)/filter, CYTHON_FILES)

cython: setup.py $(CYTHON_FILES)
	-mkdir mlfuzz
	python $< build_ext --inplace
	cp -r $(SRC_DIR)/filter mlfuzz

test: cython
	python -m test.test_mlfuzz

# afl-fuzz-orig.o: $(SRC_DIR)/afl/afl-fuzz-orig2.c
# 	$(CC) $(CFLAGS) $(SRC_DIR)/afl/afl-fuzz-orig2.c -o $@ $(LDFLAGS)

# co: $(SRC_DIR)/test.c
# 	$(CC) $(CFLAGS) $(SRC_DIR)/test.c -o a.out $(LDFLAGS)

# copy to wsl folder, runs faster in wsl directory, don't know why
in-wsl: cython
	-mkdir ~/ml-test
	-rm -r ~/ml-test/mlfuzz
	cp -r mlfuzz ~/ml-test/mlfuzz

clean:
	-rm -r ./build
	-rm -r ./*.so

.PHONY: clean
.PHONY: test
.PHONY: run-filter
