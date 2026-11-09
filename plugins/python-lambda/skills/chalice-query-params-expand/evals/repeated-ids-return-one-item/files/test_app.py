import json

from chalice.test import Client

from app import app


def test_comma_list():
    with Client(app) as client:
        body = json.loads(client.http.get("/items?ids=1,2,3").body)
    assert [i["id"] for i in body["data"]] == [1, 2, 3]
