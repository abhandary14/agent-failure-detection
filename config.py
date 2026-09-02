"""
Central configuration for the project: model selection, paths, and tunable
thresholds. Nothing here should be hardcoded elsewhere -- if you need to
change the model, a path, or a tolerance, this is the only file to edit.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent

# --- LLM backend (local Ollama server -- no API key, no cost) ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
# Ollama's default pull for this tag is a 4-bit quantized (Q4_K_M) 8B model.
# Chosen over the smaller llama3.2:3b for meaningfully more reliable native
# tool-calling while remaining free and runnable on modest hardware.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

MAX_TOKENS = 1024
MAX_TOOL_ITERATIONS = 6  # hard cap on tool-call round trips per question

# --- Data paths ---
DB_PATH = PROJECT_ROOT / "data" / "transactions.db"
LOG_DIR = PROJECT_ROOT / "logs"
TRACE_LOG_DIR = LOG_DIR / "traces"
TOOL_CALL_LOG_PATH = LOG_DIR / "tool_calls.jsonl"

# --- Retry / backoff (local server connection issues, not rate limits) ---
INTER_CALL_DELAY_SECONDS = 0.1
MAX_RETRIES = 5
RETRY_BACKOFF_BASE_SECONDS = 1.0  # 1s, 2s, 4s, 8s, 16s

# --- Flagging tolerances ---
DATE_TOLERANCE_DAYS = 0  # exact match required unless a check documents otherwise
NUMERIC_ROUNDING_TOLERANCE = 0.01  # absolute tolerance for currency comparisons

# --- Synthetic data generation ---
RANDOM_SEED = 42
NUM_USERS = 200
NUM_PRODUCTS = 20
NUM_TRANSACTIONS = 5000
PRODUCT_CATEGORIES = ["Electronics", "Home", "Apparel", "Books", "Beauty"]
