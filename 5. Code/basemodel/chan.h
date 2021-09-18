/**
 * This is a simple implementation of channel in c
 * 
 * follows the description of go channel implementation from 
 *   https://codeburst.io/diving-deep-into-the-golang-channels-549fd4ed21a8
 */
#ifndef _HAVE_CHAN_H
#define _HAVE_CHAN_H

#include "pthread.h"
#include "debug.h"
#include "stdlib.h"
#include "stdio.h"
#include "string.h"


#define CHAN_INIT_FAILED 1

typedef struct 
{
    /* data */
    int    closed;     // wheter the channel is closed
    size_t w_wait;     // number of waiting writes
    size_t r_wait;     // number of waiting reads
    size_t size;       // number of elems in the channel
    size_t capacity;   // capacity of the channel, in number of elems
    size_t dataqsize;  // size of the channel buffer
    size_t elemsize;   // size of a single element
    size_t sendx;      // pos to push the next elem
    size_t recvx;      // pos to pop the next elem
    void* buf;         // circular buffer 
    pthread_mutex_t lock;
    pthread_cond_t w_cond;
    pthread_cond_t r_cond;
} chan_t;

// initialize a channel
int chan_init(chan_t* chan, size_t elem_siz, size_t capacity);
void chan_close(chan_t* chan);
void chan_send(chan_t* chan, void* elem);
void chan_recv(chan_t* chan, void* out);

#endif