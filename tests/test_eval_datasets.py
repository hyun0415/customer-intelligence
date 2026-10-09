from eval.case_loader import load_case_dataset


def test_versioned_eval_datasets_are_loadable_and_unique():
    expected_counts = {
        "agent_review_cases.json": 15,
        "agent_policy_cases.json": 9,
        "rag_pipeline_cases.json": 24,
        "policy_access_cases.json": 11,
    }

    for filename, expected_count in expected_counts.items():
        dataset = load_case_dataset(filename)
        assert dataset.schema_version == 1
        assert dataset.dataset_version
        assert len(dataset.cases) == expected_count


def test_policy_gold_sets_record_labeling_metadata():
    for filename in ("rag_pipeline_cases.json", "policy_access_cases.json"):
        dataset = load_case_dataset(filename)
        assert dataset.labeling_method
        assert dataset.policy_scope
