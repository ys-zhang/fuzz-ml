# Changes to AFL
`go-store` is written in golang as a server to store data to a sqlite3 db
the data will be stored at `go-store/data/afl.db`

a function call is added at `afl-fuzz.c/common_fuzz_staff` to pass the input and bitmap to the go server. the two are connected through socket `/tmp/afl-store.sock`

# build

1. copy all src files to `$AFL_PATH`
2. build go-store 
    1. `cd go-store`
    2. `go install`
    3. `go build`
    4. `./go-store`, start the server
3. build afl
    1. `cd $AFL_PATH`
    2. `make clean all`
4. fuzz
