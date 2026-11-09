from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, field_validator


class Order(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: Optional[datetime] = None


class OrderCreate(BaseModel):
    sku: str
    quantity: int
    note: Optional[str] = None

    @field_validator("quantity")
    @classmethod
    def positive(cls, v):
        if v <= 0:
            raise ValueError("quantity must be positive")
        return v


class OrderFilter(BaseModel):
    ids: Optional[List[int]] = None
    status: Optional[str] = None
    limit: int = 50

    @field_validator("ids", mode="before")
    @classmethod
    def split_ids(cls, v):
        if isinstance(v, str):
            return [int(x) for x in v.split(",")]
        return v


class ResponseBody(BaseModel):
    reason: str = "ok"
    data: Optional[Any] = None
    message: Optional[str] = None
    total: Optional[int] = None
