"""Supported model catalog, defaults, and cost metadata."""

DEFAULT_LLM_PROVIDER = "openai"

DEFAULT_LLM_MODEL = {
    "openai": "gpt-4o-mini",
}

DEFAULT_JUDGE_MODEL = {
    "openai": "gpt-4.1-mini",
}

OPENAI_MODELS = [
    "gpt-5-mini",
    "gpt-5.2",
    "gpt-5-nano",
    "gpt-4o-mini",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-3.5-turbo",
]

# Model costs (USD per token)
MODEL_COSTS: dict[str, dict[str, float]] = {
    "gpt-5-mini": {"input": 0.25 / 1_000_000, "output": 2.00 / 1_000_000},
    "gpt-5.2": {"input": 1.75 / 1_000_000, "output": 14.00 / 1_000_000},
    "gpt-5-nano": {"input": 0.05 / 1_000_000, "output": 0.40 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gpt-4.1-mini": {"input": 0.40 / 1_000_000, "output": 1.60 / 1_000_000},
    "gpt-4.1-nano": {"input": 0.10 / 1_000_000, "output": 0.40 / 1_000_000},
    "gpt-3.5-turbo": {"input": 0.50 / 1_000_000, "output": 1.50 / 1_000_000},
}
