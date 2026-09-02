"""
Chatbot orchestration layer: takes a natural language question and a
session user_id, runs the tool-calling loop against the local Ollama
server, and returns a structured Trace object for the flagging layer
to analyze.
"""

import json
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from chatbot.retry import call_with_retry
from tools.schemas import TOOLS, TOOL_DISPATCH


@dataclass
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    result: Any
    timestamp: str


@dataclass
class Trace:
    trace_id: str
    question: str
    session_user_id: str
    system_prompt: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    final_response: str = ""
    total_latency_ms: float = 0.0
    raw_messages: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def build_system_prompt(session_user_id: str) -> str:
    """
    Build the system prompt, explicitly injecting today's date and the
    session user_id so the model never has to infer either.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    return (
        f"You are a business data assistant with access to tools for querying "
        f"transaction, user, and product data.\n\n"
        f"Today's date is {today}. Use this as \"today\" for any relative date "
        f"references in the user's question (e.g. \"this month\", \"last 30 days\").\n\n"
        f"The current logged-in user's ID is {session_user_id}. For any tool "
        f"that takes a user_id argument, you must use {session_user_id} unless "
        f"the question is not about a specific user's data (e.g. product or "
        f"top-seller lookups). Never use a different user_id than "
        f"{session_user_id} for this session.\n\n"
        f"Use the available tools to answer the user's question. Only call a "
        f"tool when you need data to answer -- do not call tools speculatively. "
        f"After getting tool results, give a clear, concise natural-language "
        f"answer that accurately reflects the numbers returned by the tools."
    )


def _call_ollama(messages: list[dict]) -> dict:
    """Single request to the local Ollama chat endpoint. Raises on HTTP error."""
    response = requests.post(
        f"{config.OLLAMA_BASE_URL}/api/chat",
        json={
            "model": config.OLLAMA_MODEL,
            "messages": messages,
            "tools": TOOLS,
            "stream": False,
            "options": {"num_predict": config.MAX_TOKENS},
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def _execute_tool_call(tool_call: dict) -> tuple[str, dict, Any]:
    """Execute one requested tool call. Returns (name, arguments, result)."""
    name = tool_call["function"]["name"]
    raw_args = tool_call["function"]["arguments"]
    # Ollama may return arguments as a dict already, or as a JSON string.
    arguments = raw_args if isinstance(raw_args, dict) else json.loads(raw_args)

    fn = TOOL_DISPATCH.get(name)
    if fn is None:
        result = {"error": f"Model requested unknown tool '{name}'."}
    else:
        try:
            result = fn(**arguments)
        except TypeError as exc:
            result = {"error": f"Invalid arguments for tool '{name}': {exc}"}

    return name, arguments, result


def ask(question: str, session_user_id: str) -> Trace:
    """
    Run a single question through the full tool-calling loop and return
    a structured Trace capturing every step for the flagging layer.
    """
    start_time = time.perf_counter()
    system_prompt = build_system_prompt(session_user_id)
    trace = Trace(
        trace_id=str(uuid.uuid4()),
        question=question,
        session_user_id=session_user_id,
        system_prompt=system_prompt,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    for _ in range(config.MAX_TOOL_ITERATIONS):
        time.sleep(config.INTER_CALL_DELAY_SECONDS)
        response = call_with_retry(lambda: _call_ollama(messages))
        message = response["message"]
        messages.append(message)

        tool_calls = message.get("tool_calls")
        if not tool_calls:
            trace.final_response = message.get("content", "")
            break

        for tool_call in tool_calls:
            name, arguments, result = _execute_tool_call(tool_call)
            trace.tool_calls.append(
                ToolCallRecord(
                    name=name,
                    arguments=arguments,
                    result=result,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )
            messages.append(
                {
                    "role": "tool",
                    "content": json.dumps(result, default=str),
                }
            )
    else:
        trace.final_response = (
            "[No final response: exceeded MAX_TOOL_ITERATIONS without a plain-text reply.]"
        )

    trace.raw_messages = messages
    trace.total_latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

    _save_trace(trace)
    return trace


def _save_trace(trace: Trace) -> None:
    config.TRACE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = config.TRACE_LOG_DIR / f"{ts}_{trace.trace_id[:8]}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(trace.to_dict(), f, indent=2, default=str)