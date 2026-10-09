"""Agent-level review + policy scenarios."""

from .case_loader import load_case_dataset

RAG_EVAL_CASES = load_case_dataset("agent_policy_cases.json").cases
