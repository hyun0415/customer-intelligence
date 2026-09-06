"""Evaluate Nemotron Nano 12B v2 through NVIDIA's recommended vLLM path."""

import json
import statistics
import time
from pathlib import Path

import torch
from transformers import AutoTokenizer
from vllm import LLM, SamplingParams

from colab_qwen_nemotron_ab_eval import (
    ASPECT_CASES,
    EVIDENCE_CASES,
    extract_json,
)


MODEL_ID = "nvidia/NVIDIA-Nemotron-Nano-12B-v2"
RESULT_PATH = Path("/content/nemotron_vllm_results.json")


def make_prompt(tokenizer, system: str, user: str) -> str:
    return tokenizer.apply_chat_template(
        [
            {"role": "system", "content": f"/no_think\n{system}"},
            {"role": "user", "content": user},
        ],
        tokenize=False,
        add_generation_prompt=True,
    )


def run_case(llm, sampling_params, prompt: str):
    torch.cuda.synchronize()
    started = time.perf_counter()
    result = llm.generate([prompt], sampling_params, use_tqdm=False)[0]
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    output = result.outputs[0]
    token_count = len(output.token_ids)
    return output.text, {
        "latency_s": elapsed,
        "output_tokens": token_count,
        "tokens_per_s": token_count / elapsed if elapsed else 0.0,
    }


def main():
    assert torch.cuda.is_available(), "GPU 런타임이 필요합니다."
    gpu = torch.cuda.get_device_properties(0)
    gpu_gib = gpu.total_memory / 1024**3
    assert "A100" in gpu.name and gpu_gib >= 39, "A100 런타임이 필요합니다."

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    llm = LLM(
        model=MODEL_ID,
        trust_remote_code=True,
        dtype="bfloat16",
        max_model_len=4096,
        gpu_memory_utilization=0.90,
        enforce_eager=True,
        mamba_ssm_cache_dtype="float32",
    )
    sampling_params = SamplingParams(temperature=0.0, max_tokens=384)
    rows = []
    system = "추론 과정은 출력하지 말고 요청한 JSON 객체만 반환하라."

    for case_id, question, context, expected in EVIDENCE_CASES:
        user = (
            f"질문: {question}\n근거: {context}\n"
            "질문에 직접 답할 수 있는지 판정하라. status는 sufficient, "
            "insufficient, conflict 중 하나다. "
            'JSON: {"status":"...","reason":"..."}'
        )
        raw, performance = run_case(
            llm, sampling_params, make_prompt(tokenizer, system, user)
        )
        parsed = extract_json(raw)
        rows.append(
            {
                "id": case_id,
                "task": "evidence",
                "expected": expected,
                "parsed": parsed,
                "raw": raw,
                "pass": bool(parsed and parsed.get("status") == expected),
                **performance,
            }
        )

    topics = [
        "hair_dryness",
        "hair_damage",
        "uneven_color",
        "staining",
        "odor",
        "packaging",
        "ineffective",
        "authenticity",
        "skin_reaction",
    ]
    for case_id, review, expected in ASPECT_CASES:
        user = (
            f"허용 topic: {topics}\n리뷰: {review}\n"
            "작성자의 직접 경험만 분류하라. evidence는 원문 그대로 복사하라. "
            'JSON: {"topics":["..."],"evidence":["..."]}'
        )
        raw, performance = run_case(
            llm, sampling_params, make_prompt(tokenizer, system, user)
        )
        parsed = extract_json(raw)
        actual = set(parsed.get("topics", [])) if parsed else set()
        evidence = parsed.get("evidence", []) if parsed else []
        evidence_valid = all(item in review for item in evidence)
        rows.append(
            {
                "id": case_id,
                "task": "aspect",
                "expected": expected,
                "parsed": parsed,
                "raw": raw,
                "pass": actual == set(expected) and evidence_valid,
                **performance,
            }
        )

    latencies = [row["latency_s"] for row in rows]
    throughput = [row["tokens_per_s"] for row in rows]
    parsed_count = sum(row["parsed"] is not None for row in rows)
    report = {
        "environment": {
            "gpu": gpu.name,
            "vram_gib": gpu_gib,
            "torch": torch.__version__,
            "engine": "vLLM",
            "mamba_ssm_cache_dtype": "float32",
        },
        "model": MODEL_ID,
        "cases": rows,
        "summary": {
            "case_count": len(rows),
            "pass_count": sum(row["pass"] for row in rows),
            "accuracy": sum(row["pass"] for row in rows) / len(rows),
            "json_parse_rate": parsed_count / len(rows),
            "latency_mean_s": statistics.mean(latencies),
            "latency_p50_s": statistics.median(latencies),
            "tokens_per_s_mean": statistics.mean(throughput),
            "vram_reserved_gib": torch.cuda.max_memory_reserved() / 1024**3,
        },
    }
    RESULT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"결과 저장: {RESULT_PATH}")

    try:
        from google.colab import files

        files.download(str(RESULT_PATH))
    except ImportError:
        pass


if __name__ == "__main__":
    main()
