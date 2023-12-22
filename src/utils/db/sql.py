from __future__ import annotations
import aiosqlite
from aiosqlite import Error, Row
import aiofiles
import pathlib


__all__ = (
    "execute_query",
    "db_init",
)


def dict_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}


async def create_connection() -> aiosqlite.Connection:
    connection = None
    try:
        connection = await aiosqlite.connect(pathlib.Path.cwd() / "data" / "sql" / "db.sqlite3")
        connection.row_factory = dict_factory
        print("Connection to SQLite DB successful")
    except Error as e:
        print(f"The error '{e}' occurred")
    return connection


async def execute_query(query: str, data: list[tuple] = None, connection: aiosqlite.Connection = None) -> list[dict]:
    if connection is None:
        connection = await create_connection()
    try:
        cursor = await connection.cursor()
        if isinstance(data, tuple):
            data = [data]
        res = await cursor.executemany(query, data)
        await connection.commit()
        res = await res.fetchall()
        print("Query executed successfully")
    except Error as e:
        print(f"The error '{e}' occurred")
    return res


async def db_init():
    for file_name in ["types.sql", "tables.sql"]:
        async with aiofiles.open(pathlib.Path.cwd() / "data" / "sql" / file_name, "r") as file:
            sql_file = await file.read()
        sql_commands = sql_file.split(';')
        for command in sql_commands:
            try:
                await execute_query(command)
            except Exception as e:
                print(f"Error: {e}")
