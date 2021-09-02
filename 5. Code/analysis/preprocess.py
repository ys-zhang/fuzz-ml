import sqlite3 as sql
import pandas as pd


DB_PATH = "./data/afl.db"
RAW_TBL = "data"
PRUNED_TBL = 'pruned'   # the table with duplicate rows removed
PATH_TBL = 'path'       # the table with paths and count of inputs with bitmap equales to path

X_FILE_NAME = './data/x.npz'
Y_FILE_NAME = './data/y.npz'
PATH_FILE_NAME = './data/path.npz'

def prune_db(db_path: str, tbl: str, pruned_tbl: str, distinct_path_tbl: str):
    """ remove duplicate input records in the database """
    with sql.connect(db_path) as conn:
        conn.execute(f"drop table {pruned_tbl};")
        conn.execute(f"drop table {distinct_path_tbl};")

        # create table for pruned data
        conn.execute(
            f"""
            create table if not exists {pruned_tbl} (
                input blob,
                bitmap blob
            );
            """
        )
        conn.execute(
            f"""
            create table if not exists {distinct_path_tbl} (bitmap blob);
            """
        )
        conn.execute(f"insert into {pruned_tbl} select distinct input, bitmap from {tbl};")
        conn.execute(f"insert into {distinct_path_tbl} select distinct bitmap from {tbl};")


def read_db(db_path: str, tbl: str):
    with sql.connect(db_path) as conn:
        return pd.read_sql_query(f"select * from {tbl}", conn)
