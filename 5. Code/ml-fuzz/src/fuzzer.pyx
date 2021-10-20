"""
module wraps the afl-fuzz lib
"""
cimport cython
cimport numpy as cnp
import numpy as np
from libc.stdint cimport uint8_t, uint32_t, int32_t
from libc.stdlib cimport malloc, free

cnp.import_array()


cdef BITMAP_SIZ = 1 << 16  # 64k bitmap

# from afl-fuzz.c, need to compile with afl-fuzz.c
cdef extern from 'afl-fuzz.c':
    ctypedef uint8_t  u8
    ctypedef uint32_t u32
    ctypedef unsigned long long u64
    ctypedef int32_t  s32;

    cdef struct queue_entry:
        u8* fname
        u32 len

        u8 cal_failed
        u8 trim_done
        u8 was_fuzzed
        u8 passed_det
        u8 has_new_cov
        u8 var_behavior
        u8 favored
        u8 fs_redundant

        u32 bitmap_size
        u32 exec_cksum
        u64 exec_us
        u64 handicap
        u64 depth

        u8* trace_mini
        u32 tc_ref

        queue_entry *next
        queue_entry *next100

    u8 *out_file                  # File to fuzz, if any
    u8 *in_dir                    # Input directory with test cases
    u8 *out_dir                   # Working & output directory
    u8 *doc_path                  # Path to documentation dir
    u8 *target_path               # Path to target binary
    u8  skip_deterministic        # Skip deterministic stages?
    u8  use_splicing              # Recombine input files?
    u32 exec_tmout

    u8 not_on_tty                 # stdout is not a tty

    queue_entry *queue
    queue_entry *queue_cur

    # generate inputs
    ctypedef enum seed_stage_t:
        SD_FINISH,
        # 1
        SD_FLIP_1, SD_FLIP_2, SD_FLIP_4, SD_FLIP_8, SD_FLIP_16, SD_FLIP_32,
        # 7
        SD_ARITH_8, SD_ARITH_16, SD_ARITH_32,
        # 10
        SD_INT_8, SD_INT_16, SD_INT_32,
        # 13
        SD_EXTRA_AUTO,
        # // TODO(zys) skip dictionary
        SD_HAVOC

    ctypedef struct seed_t:
        u8  doing_det;      # weather we gen det inputs from the seed  
        u32 perf_score;     # performance score of the seed

        seed_stage_t stage; # input generation state
        s32 i;              # next input index to gen in the stage

        u8  *buf
        u32 len

        u32 nrow;
        u32 ncol;
        u32* input_lens;
        u8* inputs;
        u8* bitmaps;
    

    cdef seed_t seed;

    # functions
    void setup_args(int argc, char** argv) nogil # setup fuzzer 
    void advance_seed() nogil
    u8   setup_seed(char** argv) nogil

    void gen_input(s32 max_row)
    void fuzz_seed()
    u8 * fuzz_result;
    void fuzz(u8 * x, u32 * x_len, s32 nrow, s32 ncol)

# cdef extern:
#     void* ck_alloc(u32 size);
#     void ck_free(void* buf);

cdef class ArrayWrapper:
    cdef void* data_ptr
    cdef cnp.npy_intp shape[2]

    cdef setup(self, int nrow, int ncol, void* data_ptr):
        """ Constructor for the class.
        Mallocs a memory buffer of size (n*sizeof(int)) and sets up
        the numpy array.
        Parameters:
        -----------
        n -- Length of the array.
        Data attributes:
        ----------------
        data -- Pointer to an integer array.
        alloc -- Size of the data buffer allocated.
        """
        self.data_ptr = data_ptr
        self.shape[0] = <cnp.npy_intp> nrow
        self.shape[1] = <cnp.npy_intp> ncol

    def __array__(self):
        ndarray = cnp.PyArray_SimpleNewFromData(2, self.shape,
                                cnp.NPY_BYTE, self.data_ptr)
        return ndarray

    def __dealloc__(self):
        """ Frees the array. """
        free(<void*>self.data_ptr)


# global object holds origin args to keep it in memory
_py_argv_holder = [b"afl-fuzz"]
cdef:
    char** _argv
    int _argc


def gen_x(int n):
    cdef s32 nrow, ncol
    cdef u8[:, ::1] view
    cdef u32[:] len_view
    
    gen_input(n)
    nrow = seed.nrow
    ncol = seed.ncol

    if nrow <= 0:
        return None, None
    
    view = <u8[:nrow, :ncol]> seed.inputs
    len_view = <u32[:nrow]> seed.input_lens
    rst = (
        np.asarray(view, dtype=np.uint8).copy(),
        np.asarray(len_view, dtype=np.uint32).copy()
    )
    return rst


def get_y():
    cdef u8[:, ::1] view
    if seed.nrow <= 0:
        return None
    fuzz_seed()
    view = <u8[:seed.nrow, :BITMAP_SIZ]> seed.bitmaps
    return np.asarray(view, dtype=np.uint8).copy()


def fuzz_x(cnp.ndarray[char, ndim=2] x, cnp.ndarray[u32, ndim=1] x_len):
    cdef s32 nrow, ncol
    if x is None:
        return
    nrow = x.shape[0]
    ncol = x.shape[1]
    if nrow <= 0:
        return
    xx = x.flatten()
    cdef u8[::1] _x_view = xx
    cdef u32[:] x_len_view = x_len
    cdef u8[::1] x_view = _x_view

    fuzz(&x_view[0], &x_len_view[0], nrow, ncol)
    cdef u8[:, ::1] rst = <u8[:nrow, :BITMAP_SIZ]> fuzz_result
    return np.asarray(rst, dtype=np.uint8).copy()

# ================= exported python functions ====================

# ================ #
#    FOR DEBUG     #
# ================ #

def get_input_dir():
    return in_dir

def get_out_dir():
    return out_dir

def get_target():
    return target_path

def get_timeout():
    return exec_tmout

def get_seed():
    return {
        "len": seed.len,
        "stage": seed.stage,
        "stage_idx": seed.i,
    }


# setup the fuzzer
_ARG_OP_MAP = {
    '-i': 'input_dir',
    '-o': 'output_dir',
    '-t': 'timeout',
    '-d': 'skip_deterministic',
}
_ARG_OP_MAP_REV = { v:k for k,v in _ARG_OP_MAP.items() }


def get_argv():
    cdef int i
    rst = []
    for i in range(_argc):
        s = _argv[i]
        rst.append(s)

    return rst


def setup(target: str, input_dir: str, output_dir: str, timeout: int=None,
          skip_deterministic=None, target_options: str=""):
    fuzz_args = {
        "input_dir": input_dir,
        "output_dir": output_dir,
        "timeout": str(timeout),
    }

    # create args string
    fuzz_arg_str = " ".join(f"{_ARG_OP_MAP_REV[k]} {v}" for k,v in fuzz_args.items() if v is not None)
    if skip_deterministic:
        fuzz_arg_str += ' -d'
    if not target_options.endswith("@@"):
        target_options += " @@"
    arg_str = fuzz_arg_str + f" {target} " + target_options
    global _py_argv_holder, _argc, _argv
    for s in arg_str.split():
        _py_argv_holder.append(bytes(s,'ascii'))  # only supports ascii characters
    _argc = len(_py_argv_holder)
    _argv = <char**>malloc(<size_t>(_argc+1) * sizeof(char*))
    if not _argv:
        raise MemoryError("Failed malloc for fuzz argv")

    for i in range(_argc):
        _argv[i] = _py_argv_holder[i]
    _argv[_argc] = cython.NULL  # mark end of the argv as NULLS
    with nogil:
        setup_args(_argc, _argv)
        advance_seed()

    


    
