"""
Entry point: run a single question through the chatbot pipeline and print
the trace summary. Requires a local Ollama server running with the model
configured in config.py pulled (see README).

Usage:
    python main.py "What was our revenue on P001 last month?" U0001
"""

import json
import sys

from chatbot.agent import ask


def main() -> None:
    if len(sys.argv) < 3:
        print('Usage: python main.py "<question>" <session_user_id>')
        sys.exit(1)

    question = sys.argv[1]
    session_user_id = sys.argv[2]

    print(f"Question: {question}")
    print(f"Session user: {session_user_id}")
    print("-" * 60)

    trace = ask(question, session_user_id)

    print(f"\nTool calls ({len(trace.tool_calls)}):")
    for call in trace.tool_calls:
        print(f"  - {call.name}({json.dumps(call.arguments)})")
        print(f"    -> {json.dumps(call.result, default=str)[:300]}")

    print(f"\nFinal response:\n{trace.final_response}")
    print(f"\nTotal latency: {trace.total_latency_ms} ms")


if __name__ == "__main__":
    main()