#ifndef _HAVE_AFL_FUZZ_H
#define _HAVE_AFL_FUZZ_H

#include "types.h"
#include "config.h"
/* A toggle to export some variables when building as a library. Not very
   useful for the general public. */

#ifndef AFL_LIB
#define AFL_LIB
#endif

#ifdef AFL_LIB
/* Lots of globals, but mostly for the status UI and other things where it
   really makes no sense to haul them around as function parameters. */

u8 *in_dir,        /* Input directory with test cases  */
    *out_file,     /* File to fuzz, if any             */
    *out_dir,      /* Working & output directory       */
    *sync_dir,     /* Synchronization directory        */
    *sync_id,      /* Fuzzer ID                        */
    *use_banner,   /* Display banner                   */
    *in_bitmap,    /* Input bitmap                     */
    *doc_path,     /* Path to documentation dir        */
    *target_path,  /* Path to target binary            */
    *orig_cmdline; /* Original command line            */

u32 exec_tmout; /* Configurable exec timeout (ms)   */

u64 mem_limit;       /* Memory cap for child (MB)        */
u32 cpu_to_bind = 0; /* id of free CPU core to bind      */

u8 skip_deterministic,   /* Skip deterministic stages?       */
    force_deterministic, /* Force deterministic stages?      */
    use_splicing,        /* Recombine input files?           */
    dumb_mode,           /* Run in non-instrumented mode?    */
    score_changed,       /* Scoring for favorites changed?   */
    kill_signal,         /* Signal that killed the child     */
    resuming_fuzz,       /* Resuming an older fuzzing job?   */
    timeout_given,       /* Specific timeout given?          */
    cpu_to_bind_given,   /* Specified cpu_to_bind given?     */
    not_on_tty,          /* stdout is not a tty              */
    term_too_small,      /* terminal dimensions too small    */
    uses_asan,           /* Target uses ASAN?                */
    no_forkserver,       /* Disable forkserver?              */
    crash_mode,          /* Crash mode! Yeah!                */
    in_place_resume,     /* Attempt in-place resume?         */
    auto_changed,        /* Auto-generated tokens changed?   */
    no_cpu_meter_red,    /* Feng shui on the status screen   */
    no_arith,            /* Skip most arithmetic ops         */
    shuffle_queue,       /* Shuffle input queue?             */
    bitmap_changed = 1,  /* Time to update bitmap?           */
    qemu_mode,           /* Running in QEMU mode?            */
    skip_requested,      /* Skip request, via SIGUSR1        */
    run_over10m,         /* Run time over 10 minutes?        */
    persistent_mode,     /* Running in persistent mode?      */
    deferred_mode,       /* Deferred forkserver mode?        */
    fast_cal;            /* Try to calibrate faster?         */

u8 *trace_bits; /* SHM with instrumentation bitmap  */

u8 virgin_bits[MAP_SIZE],   /* Regions yet untouched by fuzzing */
    virgin_tmout[MAP_SIZE], /* Bits we haven't seen in tmouts   */
    virgin_crash[MAP_SIZE]; /* Bits we haven't seen in crashes  */

u32 queued_paths,       /* Total number of queued testcases */
    queued_variable,    /* Testcases with variable behavior */
    queued_at_start,    /* Total number of initial inputs   */
    queued_discovered,  /* Items discovered during this run */
    queued_imported,    /* Items imported via -S            */
    queued_favored,     /* Paths deemed favorable           */
    queued_with_cov,    /* Paths with new coverage bytes    */
    pending_not_fuzzed, /* Queued but not done yet          */
    pending_favored,    /* Pending favored paths            */
    cur_skipped_paths,  /* Abandoned inputs in cur cycle    */
    cur_depth,          /* Current path depth               */
    max_depth,          /* Max path depth                   */
    useless_at_start,   /* Number of useless starting paths */
    var_byte_count,     /* Bitmap bytes with var behavior   */
    current_entry,      /* Current queue entry ID           */
    havoc_div = 1;      /* Cycle count divisor for havoc    */

u64 total_crashes,     /* Total number of crashes          */
    unique_crashes,    /* Crashes with unique signatures   */
    total_tmouts,      /* Total number of timeouts         */
    unique_tmouts,     /* Timeouts with unique signatures  */
    unique_hangs,      /* Hangs with unique signatures     */
    total_execs,       /* Total execve() calls             */
    slowest_exec_ms,   /* Slowest testcase non hang in ms  */
    start_time,        /* Unix start time (ms)             */
    last_path_time,    /* Time for most recent path (ms)   */
    last_crash_time,   /* Time for most recent crash (ms)  */
    last_hang_time,    /* Time for most recent hang (ms)   */
    last_crash_execs,  /* Exec counter at last crash       */
    queue_cycle,       /* Queue round counter              */
    cycles_wo_finds,   /* Cycles without any new paths     */
    trim_execs,        /* Execs done to trim input files   */
    bytes_trim_in,     /* Bytes coming into the trimmer    */
    bytes_trim_out,    /* Bytes coming outa the trimmer    */
    blocks_eff_total,  /* Blocks subject to effector maps  */
    blocks_eff_select; /* Blocks selected as fuzzable      */

/* Write bitmap to file. The bitmap is useful mostly for the secret
   -B option, to focus a separate fuzzing session on a particular
   interesting input without rediscovering all the others. */
void write_bitmap(void);
/* Read bitmap from file. This is for the -B option again. */
void read_bitmap(u8 *fname);

/* Configure shared memory and virgin_bits. This is called at startup. */
void setup_shm(void);
void setup_post(void);

/* Spin up fork server (instrumented mode only). The idea is explained here:

   http://lcamtuf.blogspot.com/2014/10/fuzzing-binaries-without-execve.html

   In essence, the instrumentation allows us to skip execve(), and just keep
   cloning a stopped child. So, we just execute once, and then send commands
   through a pipe. The other part of this logic is in afl-as.h. */
void init_forkserver(char **argv);

#endif

#endif