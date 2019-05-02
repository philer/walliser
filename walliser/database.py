# -*- coding: utf-8 -*-
"""
Simple ORM for a small hobby project.

TODO:
    - read-only mode
    - relations
"""

import os
from dataclasses import dataclass
from typing import Any, Mapping, Set, Tuple
import logging

import sqlite3
import json

log = logging.getLogger(__name__)


__all__ = 'Model', 'Column', 'initialize'


def adapt_sequence(items):
        return json.dumps(tuple(items))

def convert_tuple(bytestring):
        return tuple(json.loads(bytestring))
def convert_set(bytestring):
        return frozenset(json.loads(bytestring))

sqlite3.register_adapter(tuple, adapt_sequence)
sqlite3.register_adapter(list, adapt_sequence)
sqlite3.register_adapter(set, adapt_sequence)
sqlite3.register_adapter(frozenset, adapt_sequence)
sqlite3.register_converter("TUPLE", convert_tuple)
sqlite3.register_converter("FROZENSET", convert_set)

def _itercursor(cursor):
    """Generator for comfortably iterating cursor results."""
    result = cursor.fetchone()
    while result is not None:
        yield result
        result = cursor.fetchone()


@dataclass
class Column:
    """
    Descriptor for Model attributes (sql table columns).
    Heavily inspired by dataclass and SQLAlchemy.

    Not all column definition capabilities of sql/sqlite are mapped here,
    most importantly constraints.
    """

    type: str
    name: str = None
    default: Any = None
    nullable: bool = True
    primary: bool = False
    autoincrement: bool = False
    unique: bool = False
    mutable: bool = True
    observed: bool = True

    def __post_init__(self):
        # TODO implement datetime converter
        if isinstance(self.type, str):
            assert self.type in {"TEXT", "INTEGER", "REAL", "BLOB", "TIMESTAMP",
                                 "TUPLE", "FROZENSET"}
        elif isinstance(self.type, type):
            cls = self.type
            self.type = cls.__name__.upper()
            sqlite3.register_adapter(cls, cls._sqlite_adapt_)
            sqlite3.register_converter(self.type, cls._sqlite_convert_)
        else:
            raise TypeError(f"Column type must be 'str' or 'type' for column"
                            f"'{self.name}' of class '{model.__class__.__name__}'")

    def __get__(self, model, cls=None):
        return model._column_values_[self.name]

    def __set__(self, model, value):
        if not self.mutable:
            raise TypeError(f"Column '{self.name}' of class"
                            f"'{model.__class__.__name__}' is immutable.")
        if model._column_values_[self.name] != value:
            model._updated_columns_.add(self.name)
            model._column_values_[self.name] = value
            if self.observed:
                model._notify_observers_(self.name, value)

    def __delete__(self, model):
        raise TypeError(f"Can't delete Column '{self.name}' of"
                        f"class '{model.__class__.__name__}'")

    def __set_name__(self, cls, name):
        self.name = name
        try:
            cls._columns_[name] = self
        except AttributeError:
            cls._columns_ = {name: self}
        if self.primary:
            assert not hasattr(cls, '_primary_')
            cls._primary_ = name

    def to_sql(self):
        """Build a column definition for use in CREATE TABLE."""
        # https://www.sqlite.org/draft/syntax/column-constraint.html
        sql = f"{self.name} {self.type}"
        if self.primary:
            sql += " PRIMARY KEY"
            if self.autoincrement:
                sql += " AUTOINCREMENT"
        if not self.nullable:
            sql += " NOT NULL"
        if self.unique:
            sql += " UNIQUE"
        if self.default:
            sql += " DEFAULT "
            if self.type in {"INTEGER", "REAL"}:
                sql += self.default
            else:
                # let's assume we don't have quotes in there
                sql += f"'{str(self.default)}'"
        return sql


class Observable:
    """An observable object calls registered callbacks whenever one of its
    @observed methods (including @property setters) is called.
    Use this class as a mixin (via multiple inheritance) if any of your columns
    are observed.
    """
    def __init__(self):
        self._observers_ = set()

    def subscribe(self, subscriber):
        """Add a subscriber to this object's observer list"""
        self._observers_.add(subscriber)

    def unsubscribe(self, subscriber):
        """Remove a subscriber from this object's observer list"""
        self._observers_.remove(subscriber)

    def _notify_observers_(self, method_name, *args, **kwargs):
        for observer in self._observers_:
            observer.notify(self, method_name, *args, **kwargs)


class Model:
    """Base class for models in this miniature ORM"""
    _connection_: sqlite3.Connection = None

    # assumption: every subclass has its own table.
    # -> needs fix for sub-subclassing
    _subclasses_ = set()

    @classmethod
    def __init_subclass__(cls):
        super().__init_subclass__()
        Model._subclasses_.add(cls)
        if not hasattr(cls, "_columns_"):
            cls._columns_ = dict()

    @classmethod
    def create_table(cls):
        sql = ("CREATE TABLE " + cls._tablename_ + " (\n"
             + ",\n".join("    " + col.to_sql() for col in cls._columns_.values())
             + "\n)")
        log.debug(sql)
        cls._connection_.execute(sql)
        cls._connection_.commit()

    def __init__(self, **kwargs):
        super().__init__()
        self._column_values_ = colvals = dict()
        # for name, value in zip(self._columns, args):
        #     colvals[name] = value
        for name, column in self._columns_.items():
            try:
                colvals[name] = kwargs[name]
            except KeyError:
                colvals[name] = column.default
            if colvals[name] is None and not column.nullable:
                raise TypeError("Column '{}' of class '{}' cannot be NULL/None."
                                .format(column.name, self.__class__.__name__))
        self._updated_columns_ = set()

    @classmethod
    def _make(cls, iterable):
        """Create an instance relying on attribute order rather than names."""
        return cls(**dict(zip(cls._columns_, iterable)))

    @property
    def updated(self):
        """
        Were any attributes changed since this object was
        created/retrieved/stored?
        """
        return bool(self._updated_columns_)

    def __repr__(self):
        return (self.__class__.__name__ + "("
                + ", ".join(f"{name}={column.__get__(self)}"
                            for name, column in self._columns_.items())
                + ")")

    def store(self):
        """Insert this object into the database."""
        sql = ("INSERT INTO " + self._tablename_ + " ("
             + ", ".join(data)
             + ") VALUES ("
             + ",".join(f":{name}" for name in data)
             + ");")
        data = {name: value for name, value in self._column_values_.items()
                if value is not None}
        log.debug(sql)
        self._connection_.execute(sql, data)
        self._connection_.commit()

    @classmethod
    def store_many(cls, models):
        sql = ("INSERT INTO " + cls._tablename_ + " VALUES ("
             + ",".join(f":{name}" for name in cls._columns_)
             + ");")
        data = (model._column_values_ for model in models)
        log.debug(sql)
        cls._connection_.executemany(sql, data)
        cls._connection_.commit()

    def save(self, *, _commit=True):
        """Insert this object into the database."""
        if not self._updated_columns_:
            return
        data = {name: self._column_values_[name] for name in self._updated_columns_}
        sql = (f"UPDATE {self._tablename_} SET "
             + ", ".join(f"{name} = :{name}" for name in data)
             + f" WHERE {self._primary_} = :{self._primary_};")
        data[self._primary_] = self._column_values_[self._primary_]
        log.debug("%s %s", sql, data)
        self._connection_.execute(sql, data)
        if _commit:
            self._connection_.commit()
        self._updated_columns_ = set()

    @classmethod
    def save_many(cls, models):
        for model in models:
            model.save(_commit=False)
        cls._connection_.commit()

    @classmethod
    def get(cls, query: str="1", parameters=()):
        sql = "SELECT * FROM {} WHERE {};".format(cls._tablename_, query)
        log.debug(sql)
        for result in _itercursor(cls._connection_.execute(sql, parameters)):
            yield cls._make(result)

    @classmethod
    def get_by_key(cls, key: str, value: Any):
        return cls.get(query=f"{key} = :{key}", parameters={key: value})

    @classmethod
    def first(cls, query: str="1", parameters=None):
        try:
            return next(cls.get(query=query, parameters=parameters))
        except StopIteration:
            return None

    @classmethod
    def first_by_key(cls, key: str, value: Any):
        try:
            return next(cls.get_by_key(key=key, value=value))
        except StopIteration:
            return None


def initialize(database=None):
    """
    Create a connection used for all subsequent database interaction.
    Needs to be called after all Model subclasses were created but before
    any further database interaction can happen.
    """
    if database is None:
        if 'WALLISER_DATABASE_FILE' in os.environ:
            database = os.environ['WALLISER_DATABASE_FILE']
        else:
            database = os.environ['HOME'] + "/.walliser.sqlite"
    needs_tables = database == ':memory:' or not os.path.isfile(database)
    log.debug(f"Connecting to database '{database}'")
    Model._connection_ = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    if needs_tables:
        log.info("Creating new database")
        for model in Model._subclasses_:
            model.create_table()
