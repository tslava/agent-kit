import json

from chalice.test import Client

from app import app


def get(client, path):
    response = client.http.get(path)
    return response.status_code, json.loads(response.body)


def test_list_all():
    with Client(app) as client:
        status, body = get(client, "/orders")
    assert status == 200
    assert body["total"] == 3
    assert body["message"] is None


def test_filter_by_ids_comma():
    with Client(app) as client:
        status, body = get(client, "/orders?ids=1,3")
    assert status == 200
    assert [o["sku"] for o in body["data"]] == ["A100", "C300"]


def test_filter_by_status():
    with Client(app) as client:
        status, body = get(client, "/orders?status=paid")
    assert status == 200
    assert body["total"] == 2


def test_create_and_read_back():
    with Client(app) as client:
        response = client.http.post("/orders", headers={"Content-Type": "application/json"},
                                    body=json.dumps({"sku": "D400", "quantity": 3}))
        assert response.status_code == 201
        new_id = json.loads(response.body)["data"]["id"]
        status, body = get(client, f"/orders?ids={new_id}")
    assert body["data"][0]["sku"] == "D400"


def test_create_rejects_non_positive_quantity():
    with Client(app) as client:
        response = client.http.post("/orders", headers={"Content-Type": "application/json"},
                                    body=json.dumps({"sku": "E500", "quantity": 0}))
    assert response.status_code == 400
