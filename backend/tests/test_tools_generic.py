import json
import types

import pytest

from agents.tools import adapter_list_schema, adapter_read, make_generic_tools


class DummyConnector:
    def __init__(self, connector_id: str, type_: str, config: dict | None = None):
        self.connector_id = connector_id
        self.type = type_
        self.config = config or {}


def test_adapter_list_schema_passthrough():
    c = DummyConnector("c1", "postgres")
    summary = {"tables": [{"name": "public.orders", "columns": ["id", "amount"]}]}
    assert adapter_list_schema(c, summary) == summary


def test_adapter_read_postgres_sql(monkeypatch):
    import agents.tools as tools

    captured = {}

    def fake_runner(sql: str) -> str:
        captured["sql"] = sql
        return json.dumps({"columns": ["x"], "rows": [[1]], "sql": sql})

    monkeypatch.setattr(tools, "make_postgres_tool_runner", lambda cfg: fake_runner)

    c = DummyConnector("pg1", "postgres", {"url": "postgresql://u:p@h:5432/db"})
    res = adapter_read(c, {}, {"connector_id": c.connector_id, "spec": "SELECT 1"})
    assert res.get("columns") == ["x"]
    assert res.get("rows") == [[1]]
    assert "SELECT 1" in captured["sql"]


def test_adapter_read_postgres_relation_builds_sql(monkeypatch):
    import agents.tools as tools

    captured = {}

    def fake_runner(sql: str) -> str:
        captured["sql"] = sql
        return json.dumps({"columns": ["id", "amount"], "rows": [[1, 10.0]], "sql": sql})

    monkeypatch.setattr(tools, "make_postgres_tool_runner", lambda cfg: fake_runner)

    c = DummyConnector("pg2", "postgres", {"url": "postgresql://u:p@h:5432/db"})
    spec = {
        "relation": {
            "name": "public.orders",
            "columns": ["id", "amount"],
            "filters": [{"column": "id", "op": ">", "value": 10}],
            "limit": 50,
        }
    }
    res = adapter_read(c, {}, {"connector_id": c.connector_id, "spec": spec})
    sql = captured["sql"]
    assert sql.lower().startswith("select") and "from public.orders" in sql
    assert '"id"' in sql and '"amount"' in sql
    assert "limit 50" in sql.lower()
    assert res.get("columns") == ["id", "amount"]


def test_adapter_read_gsheets_entity_resolution(monkeypatch):
    import agents.tools as tools

    captured = {}

    def fake_runner(payload: str) -> str:
        captured["payload"] = payload
        return json.dumps({"columns": ["A", "B"], "rows": [["x", "y"]]})

    monkeypatch.setattr(tools, "make_gsheets_tool_runner", lambda cfg: fake_runner)

    c = DummyConnector("gs1", "google_drive", {"oauth_access_token": "x", "oauth_refresh_token": "y"})
    connector_summaries = {
        c.connector_id: {
            "tables": [
                {"name": "My File/Sheet A", "entity_id": "FILE1:Sheet A", "columns": ["A", "B"]},
            ]
        }
    }
    # Spec without entity_id; should resolve via schema tables by name
    spec = {"sheet": {"entity": "Sheet A"}, "file_id": "FILE1"}
    res = adapter_read(c, connector_summaries, {"connector_id": c.connector_id, "spec": spec})
    assert res.get("columns") == ["A", "B"]
    assert '"entity_id": "FILE1:Sheet A"' in captured["payload"]


def test_make_generic_tools_calls_on_rows(monkeypatch):
    import agents.tools as tools

    # Patch Postgres runner
    def fake_runner(sql: str) -> str:
        return json.dumps({"columns": ["x"], "rows": [[1], [2], [3]], "sql": sql})

    monkeypatch.setattr(tools, "make_postgres_tool_runner", lambda cfg: fake_runner)

    c = DummyConnector("pg3", "postgres", {"url": "postgresql://u:p@h:5432/db"})
    captured = {"called": False, "columns": None, "rows": None}

    def on_rows(connector_id, connector_type, columns, rows):
        captured["called"] = True
        captured["columns"] = columns
        captured["rows"] = rows

    tools_list = make_generic_tools([c], {}, on_rows=on_rows)
    # Expect two tools: list_schema, read
    assert len(tools_list) == 2
    names = {t.name for t in tools_list}
    assert {"list_schema", "read"}.issubset(names)

    # Invoke read tool
    read_tool = next(t for t in tools_list if t.name == "read")
    out = read_tool.invoke({"connector_id": c.connector_id, "spec": "SELECT 1"})
    assert isinstance(out, dict) and out.get("columns") == ["x"]
    assert captured["called"] is True
    assert captured["columns"] == ["x"]
    assert captured["rows"][:2] == [[1], [2]]
