#include "mlfilter.h"

#include "sys/types.h"
#include "sys/socket.h"
#include "sys/un.h"
#include "stdio.h"
#include "stdlib.h"
#include "unistd.h"


#define CHAN_SIZE 200  // size of the filter channel

static u8 *bitmap_store;
static chan_t filter_input_chan;
static chan_t filter_sample_chan;
static chan_t filter_output_chan;

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


static void run_filter_send()
{
  const u8 mode = 0;
  input_elem_t data;
  while(!filter_input_chan.closed) {
    chan_recv(&filter_input_chan, &data);
    Write(&mode, sizeof mode);
    Write(&data.len, sizeof data.len);
    Write(&data.data, data.len * sizeof(u8));
  }
}

static void run_filter_recv()
{
  while (!filter_output_chan.closed)
  {
    /* code */
  }
}
