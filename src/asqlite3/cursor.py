# asqlite3 - A clone of aiosqlite using a ThreadPoolExecutor
# Copyright (C) 2021  PikalaxALT
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sqlite3
from collections.abc import AsyncIterator, Callable, Iterable
from types import TracebackType
from typing import TYPE_CHECKING, Any, Optional

from .types import *

if TYPE_CHECKING:
    from .core import Connection


class Cursor:
    def __init__(self, connection: "Connection", cursor: sqlite3.Cursor):
        self._connection = connection
        self._cursor = cursor

    async def _execute(self, fn: Callable[[T, Any], R], *args: T, **kwargs) -> R:
        return await self._connection._execute(fn, *args, **kwargs)

    async def __aiter__(self) -> AsyncIterator:
        while rows := await self.fetchmany():
            for row in rows:
                yield row

    async def execute(self, sql: str, parameters: Optional[Iterable] = None):
        await self._execute(self._cursor.execute, sql, parameters)
        return self

    async def executemany(self, sql: str, parameters: Iterable[Iterable] = None):
        await self._execute(self._cursor.executemany, sql, parameters)
        return self

    async def executescript(self, script: str):
        await self._execute(self._cursor.executescript, script)
        return self

    async def fetchone(self):
        return await self._execute(self._cursor.fetchone)

    async def fetchmany(self, size: int = None):
        params = (size,) if size else ()
        return await self._execute(self._cursor.fetchmany, *params)

    async def fetchall(self):
        return await self._execute(self._cursor.fetchall)

    async def close(self):
        await self._execute(self._cursor.close)

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def lastrowid(self) -> int:
        return self._cursor.lastrowid

    @property
    def arraysize(self) -> int:
        return self._cursor.arraysize

    @arraysize.setter
    def arraysize(self, value: int):
        self._cursor.arraysize = value

    @property
    def description(self) -> tuple[tuple[str, None, None, None, None, None, None]]:
        return self._cursor.description

    @property
    def connection(self) -> sqlite3.Connection:
        return self._cursor.connection

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType,
    ):
        await self.close()
