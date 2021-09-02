package main

import (
	"context"
	"database/sql"
	"encoding/binary"
	"flag"
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jackc/pgx/v4/pgxpool"
	_ "github.com/mattn/go-sqlite3"
)

type bytea = []byte

const BITMAP_SIZ = 1 << 16 // 64KB
const INPUT_SIZ = 4        // 32bit for the size of the input
const BATCH_SZ = 100

// database type
type dbtype int

const (
	POSTGRE dbtype = 1
	SQLITE3 dbtype = 2
)

var DBTYPE dbtype = SQLITE3

// database connection
var PG_DBPOOL *pgxpool.Pool
var SQLITE3_DB *sql.DB

var (
	HOST     string
	MAX_CONN int
	SEM      chan struct{}

	QUERY_CR_TBL string // create table
	QUERY_INST   string // insert
)

// socket
const SOCKPATH = "/tmp/afl-store.sock"

func dprintf(format string, v ...interface{}) {
	log.Printf(format, v...)
}

func unknownDBType() {
	panic("unrecognized dbtype")
}

func setupDB(ctx context.Context) {
	var err error
	dprintf("start connecting to db...\n")
	switch DBTYPE {
	case POSTGRE:
		HOST = "postgresql://zys:aeris@yun-pc.local:5432/fuzz"
		MAX_CONN = 100
		if PG_DBPOOL, err = pgxpool.Connect(ctx, HOST); err != nil {
			panic(fmt.Sprintf("Failed to connect to DB: %s\n", HOST))
		}
	case SQLITE3:
		HOST = "./data/afl.db"
		if f, err := os.Create(HOST); err != nil {
			panic(err)
		} else {
			f.Close()
		}
		MAX_CONN = 1
		if SQLITE3_DB, err = sql.Open("sqlite3", HOST); err != nil {
			panic(fmt.Sprintf("Failed to connect to DB: %s\n", HOST))
		}
	default:
		unknownDBType()
	}
	dprintf("Connected to %s\n", HOST)
	SEM = make(chan struct{}, MAX_CONN)
}

func closeDB() {
	switch DBTYPE {
	case POSTGRE:
		PG_DBPOOL.Close()
	case SQLITE3:
		SQLITE3_DB.Close()
	}
}

func createTableAndInsertQuery(ctx context.Context) string {
	var (
		tblname      string
		sqlCreateTbl string
		insertQuery  string
		err          error
	)
	switch DBTYPE {
	case POSTGRE:
		now := time.Now()
		tblname = fmt.Sprintf("\"fuzz-%v-%v-%v-%v-%v-%v\"",
			now.Year(), now.Month(), now.Day(),
			now.Hour(), now.Minute(), now.Second())
		sqlCreateTbl = fmt.Sprintf(
			`CREATE TABLE IF NOT EXISTS %s (
			input bytea,
			bitmap bytea
		);`, tblname)
		if _, err = PG_DBPOOL.Exec(ctx, sqlCreateTbl); err != nil {
			panic(err)
		}
		insertQuery = fmt.Sprintf("INSERT INTO %s(input, bitmap) VALUES ($1, $2)", tblname)
		for i := 1; i < BATCH_SZ; i++ {
			insertQuery = insertQuery + fmt.Sprintf(", ($%d, $%d)", 2*i+1, 2*i+2)
		}
	case SQLITE3:
		tblname = "data"
		sqlCreateTbl = fmt.Sprintf(
			`CREATE TABLE IF NOT EXISTS %s (
				input BLOB,
				bitmap BLOB
			);`, tblname)
		if _, err = SQLITE3_DB.ExecContext(ctx, sqlCreateTbl); err != nil {
			panic(err)
		}
		insertQuery = fmt.Sprintf("INSERT INTO %s(input, bitmap) VALUES (?, ?)", tblname)
		for i := 1; i < BATCH_SZ; i++ {
			insertQuery = insertQuery + ", (?, ?)"
		}
	default:
		unknownDBType()
	}
	return insertQuery
}

func setupListener() *net.UnixListener {
	// unix stream is reliable and ordered

	var (
		addr     *net.UnixAddr
		listener *net.UnixListener
		err      error
	)
	if err = syscall.Access(SOCKPATH, syscall.F_OK); err == nil {
		if err = os.Remove(SOCKPATH); err != nil {
			panic("Failed to delete unix socket")
		}
	}
	if addr, err = net.ResolveUnixAddr("unix", SOCKPATH); err != nil {
		panic(fmt.Sprintf("Fail to create socket: %s\n", SOCKPATH))
	}
	if listener, err = net.ListenUnix(addr.Network(), addr); err != nil {
		panic(fmt.Sprintf("Fail to listen on socket: %s\n", SOCKPATH))
	}
	dprintf("Listen on %v ...\n", addr)
	return listener
}

func store(ctx context.Context, query string, inputs [][]byte, bitmaps [][]byte) {
	SEM <- struct{}{}
	defer func() {
		<-SEM
	}()

	args := make([]interface{}, len(inputs)*2)
	for i := 0; i < len(inputs); i++ {
		args[2*i] = inputs[i]
		args[2*i+1] = bitmaps[i]
	}

	switch DBTYPE {
	case POSTGRE:
		rst, err := PG_DBPOOL.Exec(ctx, query, args...)
		if err != nil {
			dprintf("%v\n", rst)
			panic(err)
		}
	case SQLITE3:
		rst, err := SQLITE3_DB.ExecContext(ctx, query, args...)
		if err != nil {
			dprintf("%v\n", rst)
			panic(err)
		}
	default:
		panic("Unrecognied dbtype")
	}
}

func handle_conn(ctx context.Context, conn *net.UnixConn) {
	defer func() {
		if err := conn.Close(); err != nil {
			dprintf("connection close failed")
		}
	}()
	// prepare for receiving msg
	var err error

	// connect to db and create table for the connection
	insertQuery := createTableAndInsertQuery(ctx)

	count := 0
	n := 0
	m := 0
	sample_inputs := make([][]byte, BATCH_SZ)
	sample_bitmaps := make([][]byte, BATCH_SZ)
	b_input_size := make([]byte, INPUT_SIZ)

	for {
		select {
		case <-ctx.Done():
			return
		default:
			// read length of input
			m = 0
			for m < INPUT_SIZ {
				n, err = conn.Read(b_input_size[m:])
				if err != nil {
					panic(err)
				}
				m += n
			}
			input_size := binary.LittleEndian.Uint32(b_input_size)
			if input_size == 0 {
				break //  close connection
			}
			// read input
			input := make([]byte, input_size)
			m = 0
			for m < int(input_size) {
				n, err = conn.Read(input[m:])
				if err != nil {
					panic(err)
				}
				m += n
			}

			// read bitmap
			bitmap := make([]byte, BITMAP_SIZ)
			m = 0
			for m < BITMAP_SIZ {
				n, err = conn.Read(bitmap[m:])
				if err != nil {
					panic(err)
				}
				m += n
			}

			// store training data
			if count == BATCH_SZ {
				count = 0
				go store(ctx, insertQuery, sample_inputs, sample_bitmaps)
				sample_inputs = make([][]byte, BATCH_SZ)
				sample_bitmaps = make([][]byte, BATCH_SZ)
			}
			sample_inputs[count] = input
			sample_bitmaps[count] = bitmap
			count++
		}
	}
}

func parseArgs() {
	usepg := flag.Bool("pg", false, "Use postgresql as database")
	flag.StringVar(&HOST, "host", HOST, "database connection string")
	flag.Parse()
	if *usepg {
		DBTYPE = POSTGRE
	}
}

func main() {
	parseArgs()
	ctx, _ := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)

	// set up database

	setupDB(ctx)
	defer closeDB()

	listener := setupListener()
	defer listener.Close()
	go func(l *net.UnixListener) {
		for {
			conn, err := listener.AcceptUnix()
			if err != nil {
				dprintf("Unix socket connection failed")
				continue
			}
			go handle_conn(ctx, conn)
		}
	}(listener)
	<-ctx.Done()
}
