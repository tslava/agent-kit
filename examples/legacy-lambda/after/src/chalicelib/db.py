from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, func, select

from chalicelib.models import Order, OrderCreate, OrderFilter
from chalicelib.settings import settings

metadata = MetaData()

orders = Table(
    "orders", metadata,
    Column("id", Integer, primary_key=True),
    Column("sku", String(32), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("status", String(16), nullable=False, server_default="new"),
    Column("note", String(255)),
    Column("created_at", DateTime, server_default=func.now()),
)

engine = create_engine(settings.database_dsn)


def list_orders(flt: OrderFilter):
    query = select(orders.c.id, orders.c.sku, orders.c.quantity, orders.c.status, orders.c.created_at)
    if flt.ids:
        query = query.where(orders.c.id.in_(flt.ids))
    if flt.status:
        query = query.where(orders.c.status == flt.status)
    query = query.order_by(orders.c.id).limit(flt.limit)
    with engine.connect() as connection:
        return [Order(**row) for row in connection.execute(query).mappings()]


def create_order(order: OrderCreate) -> int:
    with engine.begin() as connection:
        result = connection.execute(orders.insert().values(**order.model_dump()))
        return result.inserted_primary_key[0]
