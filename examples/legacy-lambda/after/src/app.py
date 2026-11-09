import json

from chalice import Chalice, Response
from pydantic import ValidationError

from chalicelib import db
from chalicelib.models import OrderCreate, OrderFilter, ResponseBody

app = Chalice(app_name="inventory-api")

HEADERS = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}


def respond(body: ResponseBody, status: int = 200) -> Response:
    return Response(body=body.model_dump_json(), status_code=status, headers=HEADERS)


@app.route("/orders", methods=["GET"])
def list_orders():
    params = app.current_request.query_params or {}
    try:
        flt = OrderFilter.model_validate(params)
    except ValidationError as e:
        return respond(ResponseBody(reason="invalid_field", data=json.loads(e.json())), 400)
    rows = db.list_orders(flt)
    return respond(ResponseBody(data=[r.model_dump() for r in rows], total=len(rows)))


@app.route("/orders", methods=["POST"])
def create_order():
    try:
        order = OrderCreate.model_validate(app.current_request.json_body or {})
    except ValidationError as e:
        return respond(ResponseBody(reason="invalid_field", data=json.loads(e.json())), 400)
    new_id = db.create_order(order)
    return respond(ResponseBody(data={"id": new_id}), 201)
