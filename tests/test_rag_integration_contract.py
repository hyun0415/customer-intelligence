from src.tools import AGENT_TOOLS


def test_internal_knowledge_tool_is_registered():
    names = [agent_tool.name for agent_tool in AGENT_TOOLS]
    assert names.count("get_policy_search_options_tool") == 1
    assert names.count("search_internal_knowledge_tool") == 1
