from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, validator


class Order(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: Optional[datetime]


class OrderCreate(BaseModel):
    sku: str
    quantity: int
    note: Optional[str]

    @validator("quantity")
    def positive(cls, v):
        if v <= 0:
            raise ValueError("quantity must be positive")
        return v


class OrderFilter(BaseModel):
    ids: Optional[List[int]]
    status: Optional[str]
    limit: int = 50

    @validator("ids", pre=True)
    def split_ids(cls, v):
        if isinstance(v, str):
            return [int(x) for x in v.split(",")]
        return v


class ResponseBody(BaseModel):
    reason: str = "ok"
    data: Optional[Any]
    message: Optional[str]
    total: Optional[int]
