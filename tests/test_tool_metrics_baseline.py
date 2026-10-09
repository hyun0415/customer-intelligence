from eval.reports.tool_metrics import build_tool_metrics


def test_tool_metrics_include_selection_and_argument_accuracy():
    metrics = build_tool_metrics(
        [
            {
                "id": "A1",
                "required_tools": ["tool_a"],
                "forbidden_tools": [],
                "actual_tools": ["tool_a"],
                "tool_calls": [{"name": "tool_a", "args": {"limit": 5}}],
                "expected_args": {"tool_a": {"limit": 5}},
            },
            {
                "id": "A2",
                "required_tools": ["tool_a"],
                "forbidden_tools": [],
                "actual_tools": [],
                "tool_calls": [],
            },
        ]
    )

    assert metrics["tool_selection_accuracy"] == 0.5
    assert metrics["tool_argument_cases"] == 1
    assert metrics["tool_argument_accuracy"] == 1.0
