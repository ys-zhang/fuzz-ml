#include "chan.h"

//  ==================== wrappers ========================

inline static void lock(pthread_mutex_t* mutex)
{
  if (pthread_mutex_lock(mutex)) 
    FATAL("FAILED LOCK");
}

inline static void unlock(pthread_mutex_t* mutex)
{
  if (pthread_mutex_unlock(mutex)) 
    FATAL("FAILED UNLOCK");
}

inline static void waikup(pthread_cond_t* cond)
{
  if (pthread_cond_broadcast(cond))
    FATAL("FAILED WAIKUP COND");
}

inline static void wait(pthread_cond_t* cond, pthread_mutex_t* mutex)
{
  if (pthread_cond_wait(cond, mutex))
    FATAL("FAILED WAITING");
}

int chan_init(chan_t *chan, size_t elemsize, size_t capacity) 
{
  if (chan == NULL) {
    chan = malloc(sizeof(chan_t));
  }
  if (chan == NULL) {
    return CHAN_INIT_FAILED;
  }
  
  // setup parameters
  chan->closed = 0;
  chan->w_wait = 0;
  chan->r_wait = 0;
  chan->size   = 0;
  chan->capacity = capacity;
  chan->elemsize = elemsize;
  chan->dataqsize = elemsize * capacity;
  chan->sendx = 0;
  chan->recvx = 0;
  // init buffer
  if (chan->buf != NULL) {
    chan->buf = realloc(chan->buf, chan->dataqsize);
  } else {
    chan->buf = malloc(chan->dataqsize);
  }
  if (chan->buf == NULL) {
    return CHAN_INIT_FAILED;
  }
  // init the lock
  if (   pthread_mutex_init(&chan->lock, NULL) 
      || pthread_cond_init(&chan->w_cond, NULL)
      || pthread_cond_init(&chan->r_cond, NULL)) {
    return CHAN_INIT_FAILED;
  }
  return 0;
}

// close and free the buffer
void chan_close(chan_t* chan)
{
  if (chan == NULL) return;
  lock(&chan->lock);
  chan->closed = 1;
  chan->sendx = 0;
  chan->recvx = 0;
  free(chan->buf);
  unlock(&chan->lock);
}

void chan_send(chan_t* chan, void* elem)
{
  lock(&chan->lock);
  if (chan->closed) {
    unlock(&chan->lock);
    return;
  }
  // channel if full and wait for room
  while (chan->size == chan->capacity) {
    chan->w_wait++;
    wait(&chan->w_cond, &chan->lock);
    chan->w_wait--;
  }

  memcpy(
    chan->buf + (chan->sendx) * (chan->elemsize),
    elem,
    chan->elemsize
  );

  chan->size++;
  chan->sendx++;
  if (chan->sendx >= chan->capacity) {
    chan->sendx -= chan->capacity;
  }

  if (chan->r_wait) {
    waikup(&chan->r_cond);
  }
  unlock(&chan->lock);
}

void chan_recv(chan_t* chan, void* out)
{
  lock(&chan->lock);
  if (chan->closed) {
    unlock(&chan->lock);
    return;
  }
  
  // if channel is empty
  while (!chan->size)
  {
    chan->r_wait++;
    wait(&chan->r_cond, &chan->lock);
    chan->r_wait--;
  }

  memcmp(out, 
         chan->buf + (chan->elemsize) * (chan->recvx), 
         chan->elemsize);  
  
  chan->size--;
  chan->recvx++;
  if (chan->recvx >= chan->capacity) {
    chan->recvx -= chan->capacity;
  }

  if (chan->w_wait) {
    waikup(&chan->w_cond);
  }
  unlock(&chan->lock);
}

