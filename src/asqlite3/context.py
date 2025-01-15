# asqlite3 - A clone of aiosqlite using a ThreadPoolExecutor
# Copyright (C) 2021-2025 PikalaxALT
# See LICENSE_THIRD_PARTY for the aiosqlite license

from collections.abc import Callable, Coroutine, Generator
from functools import wraps
from typing import Any, TypeVar

from typing_extensions import AsyncContextManager

from .cursor import Cursor

_T = TypeVar("_T")

__all__ = ("contextmanager",)


class Result(AsyncContextManager[_T], Coroutine[Any, Any, _T]):
    __slots__ = ("_coro", "_obj")

    def __init__(self, coro: Coroutine[Any, Any, _T]):
        self._coro = coro
        self._obj: _T

    def send(self, value) -> None:
        return self._coro.send(value)

    def throw(self, typ, val=None, tb=None) -> None:
        if val is None:
            return self._coro.throw(typ)

        if tb is None:
            return self._coro.throw(typ, val)

        return self._coro.throw(typ, val, tb)

    def close(self) -> None:
        return self._coro.close()

    def __await__(self) -> Generator[Any, None, _T]:
        return self._coro.__await__()

    async def __aenter__(self) -> _T:
        self._obj = await self._coro
        return self._obj

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if isinstance(self._obj, Cursor):
            await self._obj.close()


def contextmanager(
    method: Callable[..., Coroutine[Any, Any, _T]]
) -> Callable[..., Result[_T]]:
    @wraps(method)
    def wrapper(self, *args, **kwargs) -> Result[_T]:
        return Result(method(self, *args, **kwargs))

    return wrapper
