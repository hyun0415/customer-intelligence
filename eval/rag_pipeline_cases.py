"""Compatibility import for the versioned policy-RAG Gold Set."""

from .case_loader import load_case_dataset

RAG_PIPELINE_DATASET = load_case_dataset("rag_pipeline_cases.json")
RAG_PIPELINE_CASES = RAG_PIPELINE_DATASET.cases
