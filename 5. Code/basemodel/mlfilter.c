#include "mlfilter.h"

#include "sys/types.h"
#include "sys/socket.h"
#include "sys/un.h"
#include "stdio.h"
#include "stdlib.h"
#include "unistd.h"


#define CHAN_SIZE 200  // size of the filter channel

u8 *bitmap_store;
extern u8* trace_bits;
static struct channel filter_chan;

int sockfd; // file descriptor for the unix stream socket

u8 filter_mode = FILTER_MODE_ONE;

//  ===================  network ========================

// write bytes to the socket
inline void Write(void *buf, size_t len)
{
  size_t n;
  while (len) {
    n = write(sockfd, buf, len);
    buf = buf + (n / sizeof(u8));
    len -= n;
  }
}

inline u8 Read_filter_result()
{
  u8 rst = 1;
  while (!read(sockfd, &rst, 1)){}
  return rst;
}

inline void lock(pthread_mutex_t *mutex)
{
  int err_code = pthread_mutex_lock(mutex);
  if (err_code) 
    FATAL("failed locking: %i\n", err_code);
}

inline void unlock(pthread_mutex_t *mutex)
{
  int err_code = pthread_mutex_unlock(mutex);
  if (err_code) 
    FATAL("failed unlocking: %i\n", err_code);
}

inline void wait_cond(pthread_cond_t *cond, pthread_mutex_t *mutex)
{
  int err_code = pthread_cond_wait(cond, mutex);
  if (err_code) 
    FATAL("failed waiting: %i\n", err_code);
}

inline void cond_broadcast(pthread_cond_t *cond)
{
  int err_code = pthread_cond_broadcast(cond);
  if (err_code)
    FATAL("failed wakeup: %i\n", err_code);
}


void filter_sock_setup()
{
  int rc;
  sockfd = socket(AF_UNIX, SOCK_STREAM, 0);
  // try to connect to golang server
  struct sockaddr_un sock_addr;
  bitmap_store = calloc(MAP_SIZE, sizeof(u8));
  if (!bitmap_store) {
    printf("Failed to calloc zys_bitmap\n");
    exit(1);
  }
  memset(&sock_addr, 0, sizeof(sock_addr));
  sock_addr.sun_family = AF_UNIX;
  strcpy(sock_addr.sun_path, FILTER_SOCK);
  rc = connect(sockfd, (struct sockaddr *)&sock_addr, sizeof(sock_addr));
  if (rc < 0) {
    sprintf("Failed to connect to %s.\n", FILTER_SOCK);
    exit(1);
  }
  SAYF("filter socket connected");
}


void filter_sock_close()
{
  u32 flag = 0;
  Write(&flag, sizeof(flag));
  free(bitmap_store);
  int rc = close(sockfd);
  if (rc < 0)
  {
    printf("Faile to close client socket.\n");
    exit(1);
  }
  SAYF("filter socket closed");
}


inline void filter_feed_sample(u8 *input, u32 input_size, u8 *bitmap)
{
  // if (!in_training) return;
  
  memcpy(bitmap_store, bitmap, MAP_SIZE);
  u8 mode = 1;
  // indicates training mode
  Write(&mode, sizeof(mode));
  // write input size
  Write(&input_size, sizeof(input_size));
  // write input
  Write(input, input_size * sizeof(u8));
  // write bitmap
  Write(bitmap_store, MAP_SIZE * sizeof(u8));
}


// whether skip the input
inline u8 filter_one(u8 *input, u32 input_size)
{
  u8 mode = 0;
  // indicates in filtering mode
  Write(&mode, sizeof mode);
  // write input size
  Write(&input_size, sizeof input_size);
  // write input
  Write(input, input_size * sizeof(u8));
  return Read_filter_result();
}


// ========================== channel =======================


u8 init_chan(s32 len, struct channel *chan)
{
  chan->len = len+1;
  chan->head_idx = 0;
  chan->tail_idx = 0;
  chan->buffer = (struct channel_elem **) ck_alloc(chan->len * sizeof(struct channel_elem *));
  pthread_mutex_init(&chan->mutex, NULL);
  pthread_cond_init(&chan->cond, NULL);
  return 0;
}

void free_chan_unsafe(struct channel *chan) 
{
  if (!chan) return;
  pthread_mutex_destroy(&chan->mutex);
  pthread_cond_destroy(&chan->cond);
  for (s32 i=0; i<chan->len; i++) {
    if (!chan->buffer[i]) continue;
    if ((chan->buffer[i])->input) 
      ck_free((chan->buffer[i])->input);
    ck_free(chan->buffer[i]);
  }
  ck_free(chan->buffer);
  // ck_free(chan);
}


// the input is copied
u8 write_to_chan(struct channel *chan, u8 *in, s32 in_len) 
{
  if (!chan) return 1;
  lock(&chan->mutex);

  while ((chan->tail_idx + 1) % chan->len == chan->head_idx) {
    // channel is full
    wait_cond(&chan->cond, &chan->mutex);
  }

  struct channel_elem *elem = chan->buffer[chan->tail_idx];
  
  if (!elem) {
    elem = ck_alloc(sizeof(struct channel_elem));
    
    elem->len = in_len;
    elem->input = ck_alloc(in_len * sizeof(u8));
  } else {
    if (elem->len < in_len) {
      // ck_free(elem->input);
      elem->input = ck_realloc(elem->input, in_len * sizeof(u8)); 
    } 
    elem->len = in_len;
  }
  memcpy(elem->input, in, in_len);
  if (chan->head_idx == chan->tail_idx) {
    // before written, the channel is empty
    cond_broadcast(&chan->cond);
  }
  chan->tail_idx = (chan->tail_idx + 1) % chan->len;
  unlock(&chan->mutex);
  return 0;
}

s32 read_from_chan(struct channel *chan, u8 *out)
{
  if (!chan) return 0;
  lock(&chan->mutex);
  while (chan->head_idx == chan->tail_idx) {
    wait_cond(&chan->cond, &chan->mutex);
  }
  struct channel_elem *elem = chan->buffer[chan->head_idx];
  if (!elem) return 0;
  out = elem->input;
  if ((chan->tail_idx + 1) % chan->len == chan->head_idx) {
    // before reading the channel is full
    cond_broadcast(&chan->cond);
  }
  chan->head_idx = (chan->head_idx + 1) % chan->len;
  unlock(&chan->mutex);
  return elem->len;
}


void chan_setup()
{
  if (init_chan(200, &filter_chan)) 
    FATAL("failted init filter channel.");
}


void chan_clear()
{
  free_chan_unsafe(&filter_chan);
}


s32 read_chan(u8* output)
{
  return read_from_chan(&filter_chan, output);
}


void write_chan(u8* input, s32 input_len)
{
  if(write_to_chan(&filter_chan, input, input_len))
    FATAL("FAIL WRITE TO FILTER CHANNEL");
}


void filter_add(u8* input, u32 input_size)
{

}



 

// void run_fuzzing(char** argv)
// {
//   s32 len;
//   u8* input;
//   // u8* bitmap;
//   while (1) {
//     len = read_chan(input);
//     // common_fuzz_stuff return 1 if needs to abandon the entry
//     if (common_fuzz_stuff(argv, input, len)) continue;
//     filter_feed_sample(input, len, trace_bits);
//   }
// }

