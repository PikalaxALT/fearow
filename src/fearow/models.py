# PikalaxBOT - A Discord bot in discord.py
# Copyright (C) 2018-2021  PikalaxALT
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

import asyncio
import collections
import difflib
import functools
import inspect
import operator
import re
import sqlite3
import typing
from collections.abc import Callable, Iterable

import asyncstdlib.builtins as abuiltins
import asyncstdlib.functools as afunctools
import inflect

import asqlite3

__all__ = ("PokeapiModel",)

_T = typing.TypeVar("_T")
_R = typing.TypeVar("_R")

_garbage_pat = re.compile(r'[. \t-\'"]')
DICTIONARY = [
    "characteristic",
    "description",
    "preference",
    "pokeathlon",
    "generation",
    "experience",
    "evolution",
    "encounter",
    "condition",
    "attribute",
    "location",
    "language",
    "efficacy",
    "category",
    "version",
    "trigger",
    "sprites",
    "species",
    "pokemon",
    "pokedex",
    "machine",
    "habitat",
    "contest",
    "ailment",
    "ability",
    "target",
    "region",
    "pocket",
    "number",
    "nature",
    "method",
    "growth",
    "gender",
    "flavor",
    "effect",
    "damage",
    "change",
    "battle",
    "super",
    "style",
    "shape",
    "learn",
    "index",
    "group",
    "fling",
    "combo",
    "color",
    "class",
    "chain",
    "berry",
    "type",
    "text",
    "stat",
    "slot",
    "rate",
    "park",
    "name",
    "move",
    "meta",
    "item",
    "game",
    "form",
    "area",
    "pal",
    "map",
    "egg",
    "dex",
]
pluralizer = inflect.engine()
_prep_lock = asyncio.Lock()


def tblname_to_classname(name: str):
    name = name[11:]
    for word in DICTIONARY:
        name = name.replace(word, "_" + word.upper())
    return name.title().replace("_", "")


def sqlite3_type(coltype: str) -> type:
    if coltype.startswith("varchar"):
        return str
    return {"integer": int, "real": float, "text": str, "bool": bool}.get(coltype)


class collection(list[_T]):
    async def get(self, **attrs) -> typing.Optional[_T]:
        iscoro = inspect.isawaitable
        _all = abuiltins.all

        def attrget(key):
            attrget_sync = operator.attrgetter(key.replace("__", "."))

            async def inner(item):
                obj = attrget_sync(item)
                if iscoro(obj):
                    obj = await obj
                return obj

            return inner

        if len(attrs) == 1:
            k, v = attrs.popitem()
            pred = attrget(k.replace("__", "."))

            for elem in self:
                if await pred(elem) == v:
                    return elem
            return None

        converted = [
            (attrget(attr.replace("__", ".")), value) for attr, value in attrs.items()
        ]

        for elem in self:
            if await _all(await pred(elem) == value for pred, value in converted):
                return elem
        return None


def relationship(target: str, local_col: str, foreign_col: str, attrname: str):
    async def func(instance):
        target_cls: type["PokeapiModel"] = getattr(
            instance.classes, tblname_to_classname(target)
        )
        fk_id = getattr(instance, local_col)
        result = PokeapiModel.__cache__.get((target_cls, fk_id))
        if result is None:
            statement = (
                "select * " 'from "{}" ' "where {} = ?".format(target, foreign_col)
            )
            async with PokeapiModel._connection.execute(statement, (fk_id,)) as cursor:
                row = await cursor.fetchone()
                if row is not None:
                    result = await target_cls.from_row(row)
        return result

    func.__name__ = attrname
    return afunctools.cached_property(func)


def backref(target: str, local_col: str, foreign_col: str, attrname: str):
    async def func(instance):
        target_cls: type["PokeapiModel"] = getattr(
            instance.classes, tblname_to_classname(target)
        )
        statement = "select * " 'from "{}" ' "where {} = ?".format(target, foreign_col)
        async with PokeapiModel._connection.execute(
            statement, (getattr(instance, local_col),)
        ) as cursor:
            result = collection(
                [
                    await target_cls.from_row(row)
                    async for row in cursor
                    if row is not None
                ]
            )
        return result

    func.__name__ = attrname
    return afunctools.cached_property(func)


def name_for_scalar_relationship(
    local_cls: type["PokeapiModel"],
    dest_cls: type["PokeapiModel"],
    local_col: str,
    dest_col: str,
    constraints: Iterable[sqlite3.Row],
):
    return local_col[:-3]


def name_for_collection_relationship(
    local_cls: type["PokeapiModel"],
    dest_cls: type["PokeapiModel"],
    local_col: str,
    dest_col: str,
    constraints: Iterable[sqlite3.Row],
):
    if local_cls is dest_cls:
        return "evolves_into_species"
    parts = re.findall(r"[A-Z][a-z]+", dest_cls.__name__)
    parts[-1] = pluralizer.plural(parts[-1])
    name = "_".join(parts).lower()
    ambiguities = collections.Counter(constraint[2] for constraint in constraints)
    if ambiguities[local_cls.__tablename__] > 1:
        name += "__" + dest_col[:-3]
    return name


class classproperty:
    def __init__(self, func: Callable[[type], _R]):
        self._func = func

    def __get__(self, instance: typing.Optional[_T], owner: typing.Optional[type[_T]]):
        if owner is None:
            owner = type(instance)
        return self._func(owner)


@functools.total_ordering
class PokeapiModel:
    __abstract__ = True
    __columns__: dict[str, type] = {}
    __cache__: dict[tuple[type["PokeapiModel"], int], "PokeapiModel"] = {}
    __prepared__ = False
    classes = None
    _connection: typing.Optional[asqlite3.Connection] = None

    @classproperty
    def __tablename__(cls):
        return "pokemon_v2_" + cls.__name__.lower()

    @classmethod
    async def from_row(
        cls, row: typing.Optional[tuple]
    ) -> typing.Optional["PokeapiModel"]:
        obj = cls.__cache__.get((cls, row[0])) or cls(row)
        try:
            obj.qualified_name = await obj._qualified_name
        except AttributeError:
            pass
        return obj

    def __init__(self, row: tuple):
        if self.__abstract__:
            raise TypeError("trying to instantiate an abstract base class")
        self.__class__.__cache__[(self.__class__, row[0])] = self
        for colname, value in zip(self.__columns__, row):
            setattr(self, colname, value)
        self.qualified_name = None

    def __iter__(self):
        for column in self.__columns__:
            yield column, getattr(self, column)

    @classmethod
    async def _prepare(cls, connection: asqlite3.Connection):
        classes: dict[str, type["PokeapiModel"]] = {}
        tbl_names = [
            x
            async for x, in await connection.execute(
                "select tbl_name "
                "from sqlite_master "
                "where type = 'table' "
                "and tbl_name like 'pokemon_v2_%'"
            )
        ]
        for tbl_name in tbl_names:
            cls_name = tblname_to_classname(tbl_name)
            colspec: dict[str, type] = {
                colname: sqlite3_type(coltype)
                async for cid, colname, coltype, notnull, dflt, pk in await connection.execute(
                    'pragma table_info ("{}")'.format(tbl_name)
                )
            }

            table_cls = type(
                cls_name,
                (cls,),
                {"__abstract__": False, "__columns__": colspec} | colspec,
            )
            classes[cls_name] = table_cls
        for tbl_name in tbl_names:
            cls_name = tblname_to_classname(tbl_name)
            table_cls = classes[cls_name]
            foreign_keys = await connection.execute_fetchall(
                'pragma foreign_key_list ("{}")'.format(tbl_name)
            )
            for (
                id_,
                seq,
                dest,
                local_col,
                dest_col,
                on_update,
                on_delete,
                match,
            ) in foreign_keys:
                dest_cls_name = tblname_to_classname(dest)
                dest_cls = classes[dest_cls_name]
                manytoonekey = name_for_scalar_relationship(
                    table_cls, dest_cls, local_col, dest_col, foreign_keys
                )
                onetomanykey = name_for_collection_relationship(
                    dest_cls, table_cls, dest_col, local_col, foreign_keys
                )

                setattr(
                    table_cls,
                    manytoonekey,
                    relationship(dest, local_col, dest_col, manytoonekey),
                )
                setattr(
                    dest_cls,
                    onetomanykey,
                    backref(tbl_name, dest_col, local_col, onetomanykey),
                )
        cls.classes = type("Base", (object,), classes)

    @classmethod
    async def prepare(cls, connection: asqlite3.Connection):
        cls._connection = connection
        if not cls.__prepared__:
            async with _prep_lock:
                if not cls.__prepared__:
                    await cls._prepare(connection)
                    cls.__prepared__ = True

        differ = difflib.SequenceMatcher(lambda s: _garbage_pat.match(s) is not None)

        def fuzzy_ratio(a, b):
            differ.set_seqs(a.casefold(), b.casefold())
            return differ.ratio()

        await connection.create_function("FUZZY_RATIO", 2, fuzzy_ratio)

    @classmethod
    async def get(cls: type[_T], id_: int) -> typing.Optional[_T]:
        if (cls, id_) in cls.__cache__:
            return cls.__cache__.get((cls, id_))
        async with cls._connection.execute(
            "select * " "from {} " "where id = ?".format(cls.__tablename__), (id_,)
        ) as cur:
            row = await cur.fetchone()
        if row:
            return await cls.from_row(row)

    @classmethod
    async def get_random(cls: type[_T]) -> _T:
        async with cls._connection.execute(
            "select * " "from {} " "order by random()".format(cls.__tablename__)
        ) as cur:
            return await cls.from_row(await cur.fetchone())

    @afunctools.cached_property
    async def _qualified_name(self):
        if self.__class__.__name__ == "Language":
            attrs = {"local_language_id": 9}
            collection_name = "language_names__language"
        else:
            attrs = {"language_id": 9}
            collection_name = (
                re.sub(r"([a-z])([A-Z])", r"\1_\2", self.__class__.__name__).lower()
                + "_names"
            )
        names = await getattr(self, collection_name)
        return (await names.get(**attrs)).name

    @classmethod
    async def get_named(cls: type[_T], name: str, *, cutoff=0.9) -> typing.Optional[_T]:
        name_cls = getattr(cls.classes, cls.__name__ + "Name")
        fk_name = re.sub(r"([a-z])([A-Z])", r"\1_\2", cls.__name__).lower() + "_id"
        select = "SELECT * FROM {0} INNER JOIN {1} ON {0}.id = {1}.{2}"
        fuzzy_clause = "FUZZY_RATIO({1}.name, :name) > :cutoff"
        if hasattr(cls, "name"):
            fuzzy_clause += " OR FUZZY_RATIO({0}.name, :name) > :cutoff"
        lang_attr_name = (
            "local_language_id" if cls.__name__ == "Language" else "language_id"
        )
        lang_clause = "{1}.{3} = 9"
        statement = f"{select} WHERE {lang_clause} AND ({fuzzy_clause})".format(
            cls.__tablename__, name_cls.__tablename__, fk_name, lang_attr_name
        )
        async with cls._connection.execute(
            statement, dict(name=name, cutoff=cutoff)
        ) as cur:
            row = await cur.fetchone()
        if row:
            return await cls.from_row(row)

    def __str__(self):
        try:
            return self.qualified_name
        except AttributeError:
            return "<{0.__class__.__name__} id={0.id}>".format(self)

    def __repr__(self):
        try:
            return "<{0.__class__.__name__} id={0.id} name={0.qualified_name}>".format(
                self
            )
        except AttributeError:
            return "<{0.__class__.__name__} id={0.id}>".format(self)

    def __eq__(self, other):
        try:
            return self.__class__ is other.__class__ and self.id == other.id
        except AttributeError:
            return False

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.id < other.id
        return NotImplemented

    def __hash__(self):
        return hash((self.__class__, self.id))
