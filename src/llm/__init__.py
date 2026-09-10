"""Role-based LLM runtime configuration and clients.

Import concrete modules directly so configuration-only consumers do not load
LangChain or an OpenAI client as a package-import side effect.
"""
