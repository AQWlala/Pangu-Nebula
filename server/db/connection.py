import asyncio
import os
from typing import Optional, Any

from sqlalchemy import text

from .engine import async_session, init_db, engine


class DatabaseConnection:
    def __init__(self, db_path: str = "data/nebula.db"):
        self.db_path = db_path
        self._pool: Optional[asyncio.Semaphore] = None
        self._max_connections = 10
        self._initialized = False

    async def init(self):
        if not self._initialized:
            await init_db()
            self._initialized = True
        if self._pool is None:
            self._pool = asyncio.Semaphore(self._max_connections)

    @staticmethod
    def _bind(sql: str, args: tuple):
        if not args:
            return text(sql), {}
        params = {}
        converted = sql
        for i, arg in enumerate(args):
            param_name = f"arg_{i}"
            converted = converted.replace("?", f":{param_name}", 1)
            params[param_name] = arg
        return text(converted), params

    async def acquire(self):
        if self._pool is None:
            await self.init()
        await self._pool.acquire()
        conn = await engine.raw_connection()
        return conn

    async def release(self, conn):
        try:
            await conn.close()
        finally:
            if self._pool is not None:
                self._pool.release()

    async def execute(self, sql: str, *args):
        if self._pool is None:
            await self.init()
        await self._pool.acquire()
        try:
            stmt, params = self._bind(sql, args)
            async with async_session() as session:
                result = await session.execute(stmt, params)
                await session.commit()
                return result.lastrowid
        finally:
            self._pool.release()

    async def fetch_one(self, sql: str, *args):
        if self._pool is None:
            await self.init()
        await self._pool.acquire()
        try:
            stmt, params = self._bind(sql, args)
            async with async_session() as session:
                result = await session.execute(stmt, params)
                row = result.fetchone()
                return row if row else None
        finally:
            self._pool.release()

    async def fetch_all(self, sql: str, *args):
        if self._pool is None:
            await self.init()
        await self._pool.acquire()
        try:
            stmt, params = self._bind(sql, args)
            async with async_session() as session:
                result = await session.execute(stmt, params)
                return result.fetchall()
        finally:
            self._pool.release()

    async def fetch_val(self, sql: str, *args):
        row = await self.fetch_one(sql, *args)
        return row[0] if row else None

    async def insert(self, table: str, **kwargs):
        columns = ", ".join(kwargs.keys())
        placeholders = ", ".join(f":{k}" for k in kwargs.keys())
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        async with async_session() as session:
            result = await session.execute(text(sql), kwargs)
            await session.commit()
            return result.lastrowid

    async def update(self, table: str, where: str, **kwargs):
        set_clause = ", ".join(f"{k} = :{k}" for k in kwargs.keys())
        sql = f"UPDATE {table} SET {set_clause} WHERE {where}"
        async with async_session() as session:
            await session.execute(text(sql), kwargs)
            await session.commit()

    async def delete(self, table: str, where: str, *args):
        sql = f"DELETE FROM {table} WHERE {where}"
        stmt, params = self._bind(sql, args)
        async with async_session() as session:
            await session.execute(stmt, params)
            await session.commit()


db = DatabaseConnection()
