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


u8 filter_on;

void filter_sock_setup();
void filter_sock_close();
void filter_start_train();
void filter_start_filter();

void filter_feed_sample(u8* input, u32 input_size, u8* bitmap);

// whether skip the input
u8 filter_one(u8* input, u32 input_size);


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

 

u8 new_chan(s32 len, struct channel *chan);
void free_chan_unsafe(struct channel* chan);

s32 read_chan(struct channel *chan, u8 *out);
u8 write_chan(struct channel *chan, u8 *in, s32 in_len);

#endif