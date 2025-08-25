"""
chat_llm.py
Provider-agnostic chat streaming wrapper (LangChain-backed implementation).

This module centralizes LLM provider selection and LangChain agent construction.
Callers provide a prompt (ChatPromptTemplate), tool list, and a history provider;
the wrapper returns an async iterator of events compatible with the existing SSE loop.
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional, Callable

from sqlalchemy.orm import Session

from services.settings import get_tenant_settings, get_setting


async def stream_chat_with_tools(
    db: Session,
    tenant_id: str,
    *,
    prompt,
    tools: List[Any],
    session_id: str,
    history_provider: Callable[[str], Any],
    input_payload: Dict[str, Any],
    callbacks: Optional[List[Any]] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Build a provider-specific LangChain chat agent and stream events.

    Arguments:
      - db, tenant_id: resolve tenant settings for provider/model.
      - prompt: ChatPromptTemplate
      - tools: list of LangChain tools
      - session_id: stable id for message history windowing
      - history_provider: function(session_id) -> InMemoryChatMessageHistory
      - input_payload: dict passed to chain ({"input": str, ...})
      - callbacks: optional LangChain callbacks

    Yields: event dicts from LangChain astream_events (compatible with existing loop).
    """
    # Local imports to keep surface minimal
    from langchain_openai import ChatOpenAI
    from langchain_anthropic import ChatAnthropic
    # Prefer provider-agnostic tool-calling agent when available; fallback to OpenAI helper
    try:
        from langchain.agents import AgentExecutor, create_tool_calling_agent as _create_agent
    except Exception:
        from langchain.agents import AgentExecutor, create_openai_tools_agent as _create_agent
    from langchain_core.runnables.history import RunnableWithMessageHistory

    settings = get_tenant_settings(db, tenant_id)
    provider = str(get_setting(settings, "LLM_PROVIDER", "openai")).lower()
    model = str(get_setting(settings, "LLM_MODEL", "gpt-4o"))
    temperature = float(get_setting(settings, "LLM_TEMPERATURE", 0.0))

    # Instantiate provider-specific chat model
    if provider == "openai":
        api_key = str(get_setting(settings, "LLM_API_KEY", ""))
        base_url = str(get_setting(settings, "OPENAI_BASE_URL", "https://api.openai.com/v1"))
        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=True,
            api_key=api_key,
            base_url=base_url,
            stream_usage=True,
        )
    elif provider == "anthropic":
        api_key = str(get_setting(settings, "LLM_API_KEY", ""))
        llm = ChatAnthropic(model=model, temperature=temperature, streaming=True, api_key=api_key)
    else:
        api_key = str(get_setting(settings, "LLM_API_KEY", ""))
        llm = ChatOpenAI(model=model, temperature=temperature, streaming=True, api_key=api_key)

    # Build tools agent (OpenAI function tools compatible). This preserves current behavior
    # while allowing us to swap providers via settings without touching callers.
    agent = _create_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=False, max_iterations=6, return_intermediate_steps=False)
    runnable = RunnableWithMessageHistory(
        executor,
        history_provider,
        input_messages_key="input",
        history_messages_key="chat_history",
    )

    # Stream events through to caller
    # Simple startup retry for transient init errors
    attempts = 2
    last_err: Optional[Exception] = None
    for i in range(attempts):
        try:
            async for ev in runnable.astream_events(
                input_payload,
                config={"configurable": {"session_id": session_id}, "callbacks": callbacks or []},
                version="v2",
            ):
                yield ev
            last_err = None
            break
        except Exception as e:
            last_err = e
            if i + 1 < attempts:
                import asyncio
                await asyncio.sleep(0.5 * (2 ** i))
            else:
                raise


