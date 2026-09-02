"""
Minimal local web UI for the chatbot: a chat interface where each response
also shows its live flagging verdict. Wraps the existing chatbot.agent.ask()
and flagging.checks.combine_verdict() -- no orchestration logic lives here.

Runs in production mode for flagging: no expected_tool/expected_args are
known for a live user question, so tool_selection_check and
argument_correctness_check are skipped (as designed) and only
access_scope_check, numerical_faithfulness_check, and schema_validity_check
are live-checkable.

Usage:
    python ui/server.py
Then open http://localhost:5000 in a browser. Requires Ollama running
with the model from config.py pulled.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, jsonify, request, send_from_directory

from chatbot.agent import Trace, ask
from flagging.checks import combine_verdict
from injection.inject import applicable_injectors

app = Flask(__name__, static_folder="static", static_url_path="")

# In-memory store of real Trace objects keyed by trace_id, so an injection
# button clicked later in the same session can look up and corrupt the
# original trace. Process-local and non-persistent -- fine for a local
# single-user demo, not meant to survive a server restart.
_TRACE_STORE: dict[str, Trace] = {}


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/ask", methods=["POST"])
def handle_ask():
    body = request.get_json(force=True, silent=True) or {}
    question = (body.get("question") or "").strip()
    session_user_id = (body.get("session_user_id") or "").strip()

    if not question:
        return jsonify({"error": "question is required."}), 400
    if not session_user_id:
        return jsonify({"error": "session_user_id is required."}), 400

    trace = ask(question, session_user_id)
    verdict = combine_verdict(trace, session_user_id=session_user_id)

    _TRACE_STORE[trace.trace_id] = trace
    available_injections = [label for label, _ in applicable_injectors(trace)]

    return jsonify({
        "trace": trace.to_dict(),
        "verdict": verdict.to_dict(),
        "available_injections": available_injections,
    })


@app.route("/inject", methods=["POST"])
def handle_inject():
    body = request.get_json(force=True, silent=True) or {}
    trace_id = body.get("trace_id")
    injection_label = body.get("injection_label")
    session_user_id = (body.get("session_user_id") or "").strip()

    if trace_id not in _TRACE_STORE:
        return jsonify({"error": "Unknown trace_id (server may have restarted)."}), 404

    original_trace = _TRACE_STORE[trace_id]
    injector = dict(applicable_injectors(original_trace)).get(injection_label)
    if injector is None:
        return jsonify({"error": f"Injection '{injection_label}' is not applicable to this trace."}), 400

    try:
        corrupted_trace, ground_truth = injector(original_trace)
    except ValueError as exc:
        return jsonify({"error": f"Injection not applicable to this trace: {exc}"}), 400

    verdict = combine_verdict(corrupted_trace, session_user_id=session_user_id)

    return jsonify({
        "trace": corrupted_trace.to_dict(),
        "verdict": verdict.to_dict(),
        "ground_truth": ground_truth,
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)