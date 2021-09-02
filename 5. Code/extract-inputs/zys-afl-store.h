/*
   use unix socket to connect to golang server and store k-v pair of input:bitmap
 */

#ifndef _ZYS_AFL_STORE_


#define _ZYS_AFL_STORE_
#define ZYS_R_AFL_SOCK "/tmp/afl-store.sock"

#include "sys/types.h"
#include "sys/socket.h"
#include "sys/un.h"
#include "stdio.h"
#include "stdlib.h"
#include "unistd.h"

#include "types.h"
#include "config.h"

int zys_sockfd;  // file descriptor for the unix stream socket

u8 *zys_bitmap;

void zys_setup_sock() {
    int rc;
    zys_sockfd = socket(AF_UNIX, SOCK_STREAM,0);
    // try to connect to golang server
    struct sockaddr_un sock_addr;
    zys_bitmap = calloc(MAP_SIZE, sizeof(u8));
    if (!zys_bitmap) {
        printf("Failed to calloc zys_bitmap\n");
        exit(1);
    }
    memset(&sock_addr, 0, sizeof(sock_addr));
    sock_addr.sun_family = AF_UNIX;
    strcpy(sock_addr.sun_path,ZYS_R_AFL_SOCK);
    rc = connect(zys_sockfd, (struct sockaddr *) &sock_addr, sizeof(sock_addr));
    if (rc < 0) {
        sprintf("Failed to connect to %s.\n", ZYS_R_AFL_SOCK);
        exit(1);
    }
}

void Write(void* buf, size_t len) {
    size_t n;
    while (len) {
        n = write(zys_sockfd, buf, len);
        buf = buf + (n / sizeof(u8));
        len -= n;
    }
}

void zys_close_sock() {
    u32 flag = 0;
    Write(&flag, sizeof(flag));
    free(zys_bitmap);
    int rc = close(zys_sockfd);
    if (rc < 0) {
        printf("Faile to close client socket.\n");
        exit(1);
    }
}

void zys_store(u8* input, u32 input_size, u8* bitmap) {
    // write input size
    Write(&input_size, sizeof(input_size));   
    // write input
    Write(input, input_size * sizeof(u8));
    // write bitmap
    Write(bitmap, MAP_SIZE * sizeof(u8));
}

// int main(int argc, char** argv) {
//     zys_setup_sock();
//     u64 input_size = 1 << 10;
//     u8* input = (u8*) malloc(input_size * sizeof(u8));
//     u8* bitmap = (u8*) malloc(MAP_SIZE * sizeof(u8));
//     store(input, input_size, bitmap);
//     zys_close_sock();
//     return 0;
// }

#endif