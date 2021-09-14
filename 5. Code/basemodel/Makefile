PROGNAME    = afl
VERSION     = $(shell grep '^\#define VERSION ' config.h | cut -d '"' -f2)

PREFIX     ?= /usr/local
BIN_PATH    = $(PREFIX)/bin
HELPER_PATH = $(PREFIX)/lib/afl
DOC_PATH    = $(PREFIX)/share/doc/afl
MISC_PATH   = $(PREFIX)/share/afl


# PROGS intentionally omit afl-as, which gets installed elsewhere.

CFLAGS     ?= -O3 -funroll-loops
CFLAGS     += -Wall -D_FORTIFY_SOURCE=2 -g -Wno-pointer-sign \
	      -DAFL_PATH=\"$(HELPER_PATH)\" -DDOC_PATH=\"$(DOC_PATH)\" \
	      -DBIN_PATH=\"$(BIN_PATH)\"
LDFLAGS    += -ldl  

COMM_HDR    = alloc-inl.h config.h debug.h types.h mlfilter.h


afl-fuzz: mlfilter.c afl-fuzz.c   $(COMM_HDR)
	$(CC) $(CFLAGS) $@.c $< -o $@ $(LDFLAGS)

clean:
	-rm afl-fuzz



