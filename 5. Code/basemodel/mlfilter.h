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
#include "chan.h"

// socket name of the filter model 
#define FILTER_SOCK "/tmp/afl-mlfilter.sock"

#define FILTER_MODE_OFF 0
#define FILTER_MODE_ONE 1
#define FILTER_MODE_BAT 2


u8 filter_mode;

typedef struct {
  u32 len;
  u8* data;
} input_elem_t;

typedef struct {
    input_elem_t* input;
    u8* bitmap;
} sample_elem_t;


void filter_sock_setup();
void filter_sock_close();
void filter_start_train();
void filter_start_filter();

void filter_feed_sample(u8* input, u32 input_size, u8* bitmap);
u8 filter_one(u8* input, u32 input_size);


void init_filter_channels();
void run_filter(chan_t* input_chan);




#endif