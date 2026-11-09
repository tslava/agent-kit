---
name: sqlalchemy-v2-migration
description: >-
  Migrate SQLAlchemy 1.3/1.4 code to 2.x (Core and ORM), sorted by how each change fails:
  writes that silently stop being saved, calls that now raise (with the exact error text
  and the fix), and things that need no change. Use when upgrading SQLAlchemy 1.x to 2.0 or
  2.1, or when upgraded code shows inserts that are not persisted, empty tables in tests,
  `'Engine' object has no attribute 'execute'`, `Not an executable object`, `Column
  expression, FROM clause, or other columns clause element expected`, `must be a mapping,
  not Row`, or `The unique() method must be invoked on this Result`. Triggers on:
  sqlalchemy 1.x to 2.0, sqlalchemy 2 migration, select([...]), engine.execute, autocommit
  removed, bound metadata, Row is not a dict, session.query to select.
---

# SQLAlchemy 1.x → 2.x

The official "Major Migration Guide" lists every change. This skill sorts them by how they
fail, because that decides the order of work. Everything below behaves the same on 2.0 and
on 2.1.

## Scope: fix what breaks, leave the Query API

`session.query(...)` still works in 2.x. It is called legacy, not removed. Rewriting every
query to `select()` is a separate change, and it buries the real migration diff. In the
migration, change only what fails or warns.

## 1. The silent break: nothing commits on its own

`engine.connect()` no longer autocommits. A write inside it is rolled back when the
connection closes. No exception, no warning:

```python
with engine.connect() as conn:
    conn.execute(orders.insert().values(sku="A100"))
# 1.x: the row is saved.  2.x: the row is gone.
```

Fix it with `engine.begin()`, which commits on success, or with an explicit commit:

```python
with engine.begin() as conn:
    conn.execute(orders.insert().values(sku="A100"))
```

The same holds for an ORM `Session`: `session.execute(insert(...))` without
`session.commit()` saves nothing.

Where it bites:

- **Test seed fixtures.** The tables stay empty, and the failures look unrelated:
  `assert 0 == 3`, `assert [] == [...]`, `IndexError: list index out of range`.
- **Write paths in the app** that use Core connections.
- **Scripts and migrations** that run DDL or bulk updates through `engine.connect()`.

**Fix this first, then rerun.** Empty tables hide the next group of errors: code that
unpacks rows never runs when there are no rows.

A write test that only checks "no exception" doesn't catch this. Read the row back.

## 2. Loud breaks: the error and the fix

**Engine, connection, statements**

| 1.x code | Error in 2.x | Fix |
|---|---|---|
| `engine.execute(stmt)` | `AttributeError: 'Engine' object has no attribute 'execute'` | `with engine.connect() as conn: conn.execute(stmt)`; `engine.begin()` for writes |
| `conn.execute("SELECT 1")` | `ObjectNotExecutableError: Not an executable object: 'SELECT 1'` | `conn.execute(text("SELECT 1"))` |
| `conn.execute(stmt, a=1)` | `TypeError: Connection.execute() got an unexpected keyword argument 'a'` | `conn.execute(stmt, {"a": 1})` |
| `conn.begin()` after an `execute()` on the same connection | `InvalidRequestError: This connection has already initialized a SQLAlchemy Transaction() object via begin() or autobegin` | open the block with `engine.begin()`, or call `conn.commit()` |
| `create_engine(dsn, encoding="utf8")` | `TypeError: Invalid argument(s) 'encoding' sent to create_engine()` | drop the argument |
| `engine.has_table("orders")` | `AttributeError: 'Engine' object has no attribute 'has_table'` | `inspect(engine).has_table("orders")` |

**Statement constructors**

| 1.x code | Error in 2.x | Fix |
|---|---|---|
| `select([t.c.id, t.c.sku])` | `ArgumentError: Column expression, FROM clause, or other columns clause element expected, got [Column(...), ...]` | `select(t.c.id, t.c.sku)` |
| `case([(cond, "a")], else_="b")` | `ArgumentError: The "whens" argument to case() ... is now passed as a series of positional elements` | `case((cond, "a"), else_="b")` |
| `t.insert({"sku": "A100"})` | `TypeError: TableClause.insert() takes 1 positional argument but 2 were given` | `t.insert().values(sku="A100")` |
| `insert(t, values=...)`, `update(t, whereclause=...)` | `TypeError: ... got an unexpected keyword argument` | `.values(...)`, `.where(...)` |
| `query.filter("id = 1")` | `ArgumentError: Textual SQL expression 'id = 1' should be explicitly declared as text('id = 1')` | `text("id = 1")` |

**Rows.** A `Row` is now a named tuple, not a dict.

| 1.x code | Error in 2.x | Fix |
|---|---|---|
| `Order(**row)` | `TypeError: ... argument after ** must be a mapping, not Row` | iterate `conn.execute(stmt).mappings()` |
| `dict(row)` | `TypeError: object is not iterable` | `dict(row._mapping)` |
| `row["sku"]` | `TypeError: tuple indices must be integers or slices, not str` | `row.sku` or `row._mapping["sku"]` |
| `row.keys()`, `row.items()` | `AttributeError: Could not locate column in row for column 'keys'` | `row._mapping.keys()` |
| `from sqlalchemy.engine import RowProxy` | `ImportError` | `Row` |

**Metadata**

| 1.x code | Error in 2.x | Fix |
|---|---|---|
| `MetaData(bind=engine)` | `TypeError: MetaData.__init__() got an unexpected keyword argument 'bind'` | keep the engine separately |
| `metadata.create_all()` | `TypeError: MetaData.create_all() missing 1 required positional argument: 'bind'` | `metadata.create_all(engine)` |
| `Table("orders", metadata, autoload=True)` | `TypeError: Additional arguments should be named <dialectname>_<argument>, got 'autoload'` | `autoload_with=engine` |

**ORM**

| 1.x code | Error in 2.x | Fix |
|---|---|---|
| `Session(engine, autocommit=True)` | `ArgumentError: autocommit=True is no longer supported` | commit explicitly, or `with session.begin():` |
| `session.begin(subtransactions=True)` | `TypeError: Session.begin() got an unexpected keyword argument 'subtransactions'` | remove it |
| `session.execute(select(User)).all()`, then `user.name` | `AttributeError: name` | each item is a one-element `Row`. Use `session.scalars(select(User)).all()` |
| `select(User).options(joinedload(User.addresses))` | `InvalidRequestError: The unique() method must be invoked on this Result` | `.unique()` before `.all()` |
| a declarative model with a plain annotation, `tags: list = None` | `MappedAnnotationError: Type annotation for "User.tags" can't be correctly interpreted for Annotated Declarative Table form` | `__allow_unmapped__ = True` on the base class as a stopgap, `Mapped[...]` later |

## 3. Two changes that reach further than their line

**Removing bound metadata changes function signatures.** A helper that created an engine,
bound it and returned the `MetaData` now has to return the engine too. Every caller and
every fixture that passed that metadata around changes with it. Grep for `.bind` and
`bind=` and count the call sites before you start.

**`Inspector.has_table()` wants a name.** Old helpers were often called with a `Table`
object. Now that fails inside the dialect with an error that points nowhere useful, on
SQLite `AttributeError: 'Table' object has no attribute 'replace'`. Pass `table.name`.

## 4. No change needed

- `future=True` on `create_engine` and `sessionmaker` is accepted and does nothing in 2.x.
  Remove it when you see it.
- `Table`, `Column` and dialect types (`JSONB`, `ARRAY`, `ENUM`) are unchanged.
- `from sqlalchemy.ext.declarative import declarative_base` still imports, with a
  `MovedIn20Warning`. Import it from `sqlalchemy.orm`.
- `session.query(User).get(1)` works with a `LegacyAPIWarning`. `session.get(User, 1)` is
  the replacement.

## Size the job first

```bash
# silent: writes that relied on autocommit
grep -rnE "\.connect\(\)|autocommit|subtransactions" src tests
# statements and execution
grep -rnE "engine\.execute\(|select\(\[|case\(\[|\.insert\([^)]|whereclause=|\.execute\(\s*[\"']" src tests
# rows
grep -rnE "\*\*row|dict\(row\)|row\[[\"']|RowProxy" src tests
# metadata
grep -rnE "\.bind|bind=|autoload=True|has_table" src tests
# ORM
grep -rnE "joinedload|session\.execute\(select|declarative_base" src tests
```

## Order of work

1. Autocommit (section 1), in the fixtures first and then in the app.
2. Statement constructors and execution.
3. Row access.
4. Metadata and helper signatures.
5. ORM results.

Run the tests after each step. Each fix uncovers the next layer.

For a large codebase, SQLAlchemy 1.4 is a useful bridge. It runs both styles, and with
`SQLALCHEMY_WARN_20=1` it emits a `RemovedIn20Warning` at every call that 2.0 removes, so
the test run gives you the list of call sites. For a small service, go straight to 2.x
with the greps above.

## Verify

- The suite is green, and the write tests read their rows back.
- `uv run pytest -W error::sqlalchemy.exc.SADeprecationWarning` shows the legacy calls that
  still work, such as `Query.get()` and the old `declarative_base` import.
- `sqlalchemy>=2.0` resolves to the newest 2.x. Check the version in the lockfile and read
  that minor version's changelog if something fails that this list doesn't explain.
