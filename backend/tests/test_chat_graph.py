import asyncio
import json
import uuid
import os

import pytest

import agents.chat_graph as cg


class DummyConnector:
    def __init__(self, connector_id: str, type_: str, config: dict | None = None):
        self.connector_id = connector_id
        self.type = type_
        self.config = config or {}


class FakeQueryList:
    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    def __init__(self, connectors):
        self._connectors = connectors

    def query(self, model):
        # Only connectors are queried here; other data loads are monkeypatched
        if model is cg.Connector:
            return FakeQueryList(self._connectors)
        return FakeQueryList([])


class FakeAgentExecutor:
    def __init__(self, agent=None, tools=None, verbose=False, max_iterations=None, return_intermediate_steps=False):
        self.agent = agent
        self.tools = tools or []
        self.return_intermediate_steps = return_intermediate_steps

    def invoke(self, inputs):
        # Return output and an observation with tabular data to test preview capture
        return {
            "output": "Here is your answer.",
            "intermediate_steps": [
                (None, {
                    "columns": ["a"],
                    "rows": [[1], [2], [3]],
                    "connector_id": "pg1",
                    "connector_type": "postgres",
                })
            ],
        }

    async def astream_events(self, inputs, version="v2", **kwargs):
        class Chunk:
            def __init__(self, content: str):
                self.content = content
        # Stream a token, a tool lifecycle with a large rows payload, then a final output
        yield {"event": "on_llm_stream", "data": {"chunk": Chunk("Hello ")}}
        yield {"event": "on_llm_stream", "data": {"chunk": Chunk("world!")}}
        yield {"event": "on_tool_start", "name": "read", "data": {"input": {"connector_id": "pg1"}}}
        yield {"event": "on_tool_end", "data": {"output": {"columns": ["a"], "rows": [[i] for i in range(10)]}}}
        yield {"event": "on_chain_end", "data": {"output": "All done."}}


def test_run_chat_agent_removed(monkeypatch):
    with pytest.raises(RuntimeError):
        cg.run_chat_agent(object(), uuid.uuid4(), "hello")


@pytest.mark.asyncio
async def test_run_chat_agent_stream_sends_events(monkeypatch):
    # Patch LLM/Agent scaffolding
    monkeypatch.setattr(cg, "_make_llm", lambda: object())
    monkeypatch.setattr(cg, "create_openai_tools_agent", lambda llm, tools, prompt: object())
    monkeypatch.setattr(cg, "AgentExecutor", FakeAgentExecutor)

    # Patch data loaders
    monkeypatch.setattr(cg, "_load_canonical_summary", lambda db, tenant_id: {"unified_entities": []})
    monkeypatch.setattr(cg, "_load_connector_schemas", lambda db, tenant_id, connectors: {str(connectors[0].connector_id): {"tables": []}})

    connectors = [DummyConnector("pg1", "postgres", {"url": "postgresql://u:p@h:5432/db"})]
    db = FakeSession(connectors)

    gen = cg.run_chat_agent_stream(db, uuid.uuid4(), "hello")

    events = []
    tool_end_payload = None
    async for sse in gen:
        # Parse SSE lines
        lines = [ln for ln in sse.strip().split("\n") if ln]
        if not lines:
            continue
        if lines[0].startswith("event:"):
            ev = lines[0].split(":", 1)[1].strip()
            events.append(ev)
            if ev == "tool_end" and len(lines) > 1 and lines[1].startswith("data:"):
                data_json = lines[1].split(":", 1)[1].strip()
                try:
                    tool_end_payload = json.loads(data_json)
                except Exception:
                    pass

    # Verify key events were emitted and tool_end rows were truncated to 5
    assert "ready" in events
    assert "token" in events
    assert "tool_start" in events
    assert "tool_end" in events
    assert "final" in events
    assert "done" in events
    assert isinstance(tool_end_payload, dict)
    assert tool_end_payload.get("rows") is not None and len(tool_end_payload["rows"]) == 5


@pytest.mark.asyncio
async def test_thread_memory_across_turns(monkeypatch):
    # Patch LLM/Agent scaffolding
    monkeypatch.setattr(cg, "_make_llm", lambda: object())
    monkeypatch.setattr(cg, "create_openai_tools_agent", lambda llm, tools, prompt: object())
    monkeypatch.setattr(cg, "AgentExecutor", FakeAgentExecutor)

    # Patch data loaders
    monkeypatch.setattr(cg, "_load_canonical_summary", lambda db, tenant_id: {"unified_entities": []})
    monkeypatch.setattr(cg, "_load_connector_schemas", lambda db, tenant_id, connectors: {str(connectors[0].connector_id): {"tables": []}})

    connectors = [DummyConnector("pg1", "postgres", {"url": "postgresql://u:p@h:5432/db"})]
    db = FakeSession(connectors)

    hist = cg.MessageHistory()
    hist.add_message("user", "hello")
    hist.add_message("assistant", "world")
    hist.add_message("user", "foo")
    hist.add_message("assistant", "bar")

    gen = cg.run_chat_agent_stream(db, uuid.uuid4(), "hello", hist)

    events = []
    tool_end_payload = None
    async for sse in gen:
        # Parse SSE lines
        lines = [ln for ln in sse.strip().split("\n") if ln]
        if not lines:
            continue
        if lines[0].startswith("event:"):
            ev = lines[0].split(":", 1)[1].strip()
            events.append(ev)
            if ev == "tool_end" and len(lines) > 1 and lines[1].startswith("data:"):
                data_json = lines[1].split(":", 1)[1].strip()
                try:
                    tool_end_payload = json.loads(data_json)
                except Exception:
                    pass

    # Verify key events were emitted and tool_end rows were truncated to 5
    assert "ready" in events
    assert "token" in events
    assert "tool_start" in events
    assert "tool_end" in events
    assert "final" in events
    assert "done" in events
    assert isinstance(tool_end_payload, dict)
    assert tool_end_payload.get("rows") is not None and len(tool_end_payload["rows"]) == 5
    assert len(getattr(hist, "messages", [])) >= 4


@pytest.mark.asyncio
async def test_history_windowing_trim(monkeypatch):
    # Keep only 1 turn (2 messages) in history
    monkeypatch.setenv("CHAT_HISTORY_MAX_TURNS", "1")

    # Patch LLM/Agent scaffolding
    monkeypatch.setattr(cg, "_make_llm", lambda: object())
    monkeypatch.setattr(cg, "create_openai_tools_agent", lambda llm, tools, prompt: object())
    monkeypatch.setattr(cg, "AgentExecutor", FakeAgentExecutor)

    # Patch data loaders
    monkeypatch.setattr(cg, "_load_canonical_summary", lambda db, tenant_id: {"unified_entities": []})
    monkeypatch.setattr(
        cg,
        "_load_connector_schemas",
        lambda db, tenant_id, connectors: {str(connectors[0].connector_id): {"tables": []}},
    )

    # Reset histories to isolate test
    cg._THREAD_HISTORIES.clear()

    connectors = [DummyConnector("pg1", "postgres", {"url": "postgresql://u:p@h:5432/db"})]
    db = FakeSession(connectors)
    tenant_id = uuid.uuid4()
    thread_id = "t1"

    # First turn
    gen1 = cg.run_chat_agent_stream(db, tenant_id, "first", thread_id)
    async for _ in gen1:
        pass

    # Second turn
    gen2 = cg.run_chat_agent_stream(db, tenant_id, "second", thread_id)
    async for _ in gen2:
        pass

    # Force a retrieval to apply trimming logic, then inspect messages length
    session_id = cg._session_key(tenant_id, thread_id)
    hist = cg._history_for_session(session_id)
    msgs = getattr(hist, "messages", [])
    assert isinstance(msgs, list) and len(msgs) <= 2  # 2 messages = 1 user/assistant turn
    assert len(msgs) > 0


def test_thread_lifecycle_helpers():
    tenant_id = uuid.uuid4()
    # Create thread
    tid = cg.create_thread(tenant_id)
    assert isinstance(tid, str) and len(tid) > 0
    # List includes the new thread
    threads = cg.list_threads(tenant_id)
    assert tid in threads
    # Delete succeeds
    ok = cg.delete_thread(tenant_id, tid)
    assert ok is True
    # List no longer includes
    threads2 = cg.list_threads(tenant_id)
    assert tid not in threads2
