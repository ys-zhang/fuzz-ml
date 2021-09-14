/*
   use unix socket to connect to golang server and store k-v pair of input:bitmap
 */

#ifndef _HAVE_ML_FILTER_H
#define _HAVE_ML_FILTER_H

#include <pthread.h>

#include "types.h"
#include "alloc-inl.h"
#include "config.h"
#include "debug.h"

// socket name of the filter model 
#define FILTER_SOCK "/tmp/afl-mlfilter.sock"

#define FILTER_MODE_OFF 0
#define FILTER_MODE_ONE 1
#define FILTER_MODE_BAT 2


u8 filter_mode;


void filter_sock_setup();
void filter_sock_close();
void filter_start_train();
void filter_start_filter();

void filter_feed_sample(u8* input, u32 input_size, u8* bitmap);

// whether skip the input
u8 filter_one(u8* input, u32 input_size);

void filter_add(u8* input, u32 input_size);

// channel for pipelining
struct channel_elem
{
    s32 len;
    u8 *input;
};


struct channel
{
    s32 len, head_idx, tail_idx;
    struct channel_elem **buffer;
    pthread_mutex_t mutex;
    pthread_cond_t cond;
};

void chan_setup();
void chan_clear(); 

s32 read_chan(u8* output);
void write_chan(u8* input, s32 input_len);


// u8 new_chan(s32 len, struct channel *chan);
// void free_chan_unsafe(struct channel* chan);



// s32 read_chan(struct channel *chan, u8 *out);
// u8 write_chan(struct channel *chan, u8 *in, s32 in_len);


// u8 common_fuzz_stuff(char** argv, u8* out_buf, u32 len);


#endif