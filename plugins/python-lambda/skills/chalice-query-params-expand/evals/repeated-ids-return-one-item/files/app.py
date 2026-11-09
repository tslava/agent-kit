from typing import List, Optional

from chalice import Chalice
from pydantic import BaseModel, field_validator

app = Chalice(app_name="items")
ITEMS = {i: {"id": i, "name": f"item-{i}"} for i in range(1, 6)}


class ItemFilter(BaseModel):
    ids: Optional[List[int]] = None

    @field_validator("ids", mode="before")
    @classmethod
    def split(cls, value):
        if isinstance(value, str):
            return [int(v) for v in value.split(",")]
        if isinstance(value, int):
            return [value]
        return value


@app.route("/items")
def list_items():
    flt = ItemFilter.model_validate(app.current_request.query_params or {})
    ids = flt.ids or list(ITEMS)
    return {"data": [ITEMS[i] for i in ids if i in ITEMS]}
