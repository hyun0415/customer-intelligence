"""A100 80GB용 Qwen/Nemotron 한국어 Agent 시범 비교."""

import gc
import json
import re
import shutil
import statistics
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


CACHE_ROOT = Path("/content/model_cache")
RESULT_PATH = Path("/content/qwen_nemotron_ab_results.json")

SMALL_MODELS = [
    "Qwen/Qwen3-8B",
    "nvidia/NVIDIA-Nemotron-Nano-12B-v2",
]
AGENT_MODELS = [
    "Qwen/Qwen3-30B-A3B-Instruct-2507",
    "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16",
]

EVIDENCE_CASES = [
    (
        "EV01",
        "동일 주문의 동일 사고에 무료 재배송은 몇 회까지 가능한가?",
        "동일 주문의 동일 사고에 대한 무료 재배송은 1회로 제한한다. "
        "2회차는 환불 또는 관리자 예외 처리 대상이다.",
        "sufficient",
    ),
    (
        "EV02",
        "배송 분실 시 1억원 현금 보상이 승인되어 있는가?",
        "배송 분실은 30일 이내 재배송을 요청할 수 있다. "
        "총 처리 가치 150,000원 초과는 CS 관리자가 승인한다.",
        "insufficient",
    ),
    (
        "EV03",
        "고객이 입원과 의료 증상을 언급하면 어떤 절차가 우선인가?",
        "의료 증상, 부상 또는 입원 언급은 금액과 관계없이 즉시 "
        "안전 담당자에게 escalation한다. CS는 진단하지 않는다.",
        "sufficient",
    ),
    (
        "EV04",
        "일본 관할에서 파손 상품을 환불할 수 있는가?",
        "관할: KR. 파손 상품은 수령 후 30일 이내 환불을 신청할 수 있다.",
        "insufficient",
    ),
    (
        "EV05",
        "하자 상품 환불 접수 기한은 며칠인가?",
        "정책 A(동일 authority, current): 30일 이내. "
        "정책 B(동일 authority, current): 14일 이내.",
        "conflict",
    ),
    (
        "EV06",
        "B00UNKNOWN 상품의 전용 CS 가이드를 알려줘.",
        "이 전용 가이드는 parent ASIN B00RWCDM4A에만 적용한다.",
        "insufficient",
    ),
]

ASPECT_CASES = [
    ("AS01", "제품을 열자 곰팡이 같은 악취가 너무 심했습니다.", ["odor"]),
    ("AS02", "상자가 젖고 병의 밀봉이 뜯겨 내용물이 샜습니다.", ["packaging"]),
    (
        "AS03",
        "사용 후 머릿결이 짚처럼 뻣뻣해졌고 색도 얼룩덜룩했습니다.",
        ["hair_dryness", "uneven_color"],
    ),
    ("AS04", "세 번 사용했지만 노란 기가 전혀 줄지 않았습니다.", ["ineffective"]),
    ("AS05", "샴푸를 쓴 뒤 두피가 붉어지고 가려웠습니다.", ["skin_reaction"]),
    (
        "AS06",
        "다른 리뷰에서 머리가 빠졌다고 하던데 저는 아직 사용하지 않았습니다.",
        [],
    ),
]

TOOL_CASES = [
    (
        "TL01",
        "동일 주문의 동일 사고에 무료 재배송은 몇 회까지 가능한가?",
        "search_internal_knowledge_tool",
        {},
    ),
    (
        "TL02",
        "배송 분실 시 1억원의 현금 보상이 승인되어 있는가?",
        "search_internal_knowledge_tool",
        {},
    ),
    (
        "TL03",
        "고객이 입원과 의료 증상을 언급하면 어떤 절차를 우선해야 하는가?",
        "search_internal_knowledge_tool",
        {},
    ),
    (
        "TL04",
        "ASIN B005IHT8KI 제품의 제목, 브랜드, 가격과 평균 평점을 알려줘.",
        "get_product_tool",
        {"parent_asin": "B005IHT8KI"},
    ),
    (
        "TL05",
        "ASIN B005IHT8KI 제품의 평점 분포를 알려줘.",
        "get_rating_distribution_tool",
        {"parent_asin": "B005IHT8KI"},
    ),
    (
        "TL06",
        "ASIN B005IHT8KI에서 helpful_vote 1 이상인 3점 이하 리뷰를 "
        "공감 투표순으로 정확히 3개 조회해줘.",
        "get_helpful_reviews_tool",
        {
            "parent_asin": "B005IHT8KI",
            "limit": 3,
            "rating_max": 3,
            "min_helpful_votes": 1,
        },
    ),
]

ANSWER_CASES = [
    (
        "AN01",
        "동일 사고의 무료 재배송은 몇 회인가?",
        "status=ok; 무료 재배송 1회. 2회차는 관리자 예외 결정.",
        ["1회", "관리자"],
        [],
    ),
    (
        "AN02",
        "배송 분실 시 1억원 현금 보상이 승인됐는가?",
        "status=no_evidence; 1억원 현금 보상 근거 없음.",
        ["근거"],
        ["승인되어 있습니다", "승인됐다"],
    ),
    (
        "AN03",
        "입원과 의료 증상을 언급하면?",
        "status=ok; 즉시 안전 담당자에게 escalation. CS는 진단하지 않음.",
        ["즉시", "안전", "escalation"],
        [],
    ),
    (
        "AN04",
        "B005IHT8KI 상품 기본 정보를 알려줘.",
        "price=38.98 USD; average_rating=4.6; rating_number=25383; DB review_count=2091.",
        ["38.98", "4.6", "25383", "2091"],
        [],
    ),
    (
        "AN05",
        "B005IHT8KI의 평점 분포와 3점 이하 비율은?",
        "합계 2091; 3점 이하 406건, 19.4%.",
        ["2091", "406", "19.4"],
        [],
    ),
    (
        "AN06",
        "조건에 맞는 공감 리뷰 3개를 알려줘.",
        "평점/공감: 2/129; 1/126; 1/30.",
        ["129", "126", "30"],
        [],
    ),
]

TOOL_SCHEMA = """사용 가능한 도구:
- search_internal_knowledge_tool(query, collections=null, parent_asin=null, limit=5)
- get_product_tool(parent_asin)
- get_rating_distribution_tool(parent_asin)
- get_helpful_reviews_tool(parent_asin, limit=10, rating_max=null, min_helpful_votes=1)
첫 번째로 호출할 도구 하나만 JSON으로 반환하라:
{"tool_name":"...","arguments":{...}}
"""


def extract_json(text: str):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            return decoder.raw_decode(text[index:])[0]
        except json.JSONDecodeError:
            pass
    return None


def normalized(text: str) -> str:
    return text.replace(",", "").replace(" ", "").lower()


def generate(model, tokenizer, system: str, user: str, max_new_tokens: int = 384):
    if "nemotron" in tokenizer.name_or_path.lower():
        system = f"/no_think\n{system}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
    except Exception:
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()
    started = time.perf_counter()
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    output_tokens = output.shape[-1] - inputs.input_ids.shape[-1]
    text = tokenizer.decode(
        output[0, inputs.input_ids.shape[-1] :],
        skip_special_tokens=True,
    )
    return text, {
        "latency_s": elapsed,
        "output_tokens": int(output_tokens),
        "tokens_per_s": output_tokens / elapsed,
        "peak_vram_gib": torch.cuda.max_memory_allocated() / 1024**3,
    }


def load_model(model_id: str):
    cache_dir = CACHE_ROOT / re.sub(r"[^A-Za-z0-9_.-]", "_", model_id)
    tokenizer = AutoTokenizer.from_pretrained(
        model_id,
        trust_remote_code=False,
        cache_dir=cache_dir,
    )
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        trust_remote_code=False,
        cache_dir=cache_dir,
        torch_dtype=torch.bfloat16,
        device_map={"": 0},
        low_cpu_mem_usage=True,
    )
    model.eval()
    return model, tokenizer, cache_dir


def cleanup(model, tokenizer, cache_dir: Path):
    del model, tokenizer
    gc.collect()
    torch.cuda.empty_cache()
    time.sleep(2)
    shutil.rmtree(cache_dir, ignore_errors=True)


def args_match(actual: dict, expected: dict) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def evaluate_small(model_id: str) -> list[dict]:
    model, tokenizer, cache_dir = load_model(model_id)
    rows = []
    system = "추론 과정은 출력하지 말고 요청한 JSON 객체만 반환하라."

    for case_id, question, context, expected in EVIDENCE_CASES:
        user = (
            f"질문: {question}\n근거: {context}\n"
            "질문에 직접 답할 수 있는지 판정하라. status는 sufficient, "
            "insufficient, conflict 중 하나다. "
            'JSON: {"status":"...","reason":"..."}'
        )
        raw, performance = generate(model, tokenizer, system, user)
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
        raw, performance = generate(model, tokenizer, system, user)
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

    cleanup(model, tokenizer, cache_dir)
    return rows


def evaluate_agent(model_id: str) -> list[dict]:
    model, tokenizer, cache_dir = load_model(model_id)
    rows = []
    system = (
        "당신은 한국어 Customer Intelligence Agent다. 추론 과정은 출력하지 "
        "말고 주어진 도구와 근거만 사용한다."
    )

    for case_id, question, expected_tool, expected_args in TOOL_CASES:
        raw, performance = generate(
            model,
            tokenizer,
            system,
            f"{TOOL_SCHEMA}\n사용자 질문: {question}",
        )
        parsed = extract_json(raw)
        actual_args = parsed.get("arguments", {}) if parsed else {}
        passed = bool(
            parsed
            and parsed.get("tool_name") == expected_tool
            and args_match(actual_args, expected_args)
        )
        rows.append(
            {
                "id": case_id,
                "task": "tool_call",
                "expected_tool": expected_tool,
                "expected_args": expected_args,
                "parsed": parsed,
                "raw": raw,
                "pass": passed,
                **performance,
            }
        )

    for case_id, question, tool_output, required, forbidden in ANSWER_CASES:
        raw, performance = generate(
            model,
            tokenizer,
            system,
            (
                f"사용자 질문: {question}\n도구 결과: {tool_output}\n"
                "도구 결과에 없는 사실을 만들지 말고 한국어로 간결하게 답하라."
            ),
            max_new_tokens=512,
        )
        clean = normalized(raw)
        passed = all(normalized(item) in clean for item in required) and not any(
            normalized(item) in clean for item in forbidden
        )
        rows.append(
            {
                "id": case_id,
                "task": "grounded_answer",
                "required": required,
                "forbidden": forbidden,
                "raw": raw,
                "pass": passed,
                **performance,
            }
        )

    cleanup(model, tokenizer, cache_dir)
    return rows


def summarize(rows: list[dict]) -> dict:
    latency = [row["latency_s"] for row in rows]
    throughput = [row["tokens_per_s"] for row in rows]
    return {
        "case_count": len(rows),
        "pass_count": sum(row["pass"] for row in rows),
        "accuracy": sum(row["pass"] for row in rows) / len(rows),
        "json_parse_rate": sum(row.get("parsed") is not None for row in rows)
        / len(rows),
        "latency_mean_s": statistics.mean(latency),
        "latency_p50_s": statistics.median(latency),
        "tokens_per_s_mean": statistics.mean(throughput),
        "peak_vram_gib": max(row["peak_vram_gib"] for row in rows),
    }


def save_report(report: dict):
    RESULT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"결과 저장: {RESULT_PATH}")


def main():
    assert torch.cuda.is_available(), "GPU 런타임이 필요합니다."
    gpu = torch.cuda.get_device_properties(0)
    gpu_gib = gpu.total_memory / 1024**3
    print({"gpu": gpu.name, "vram_gib": round(gpu_gib, 1)})
    assert "A100" in gpu.name and gpu_gib >= 39, "A100 런타임이 필요합니다."
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)

    report = {
        "environment": {
            "gpu": gpu.name,
            "vram_gib": gpu_gib,
            "torch": torch.__version__,
        },
        "models": {},
        "summary": {},
    }
    model_plan = [*((model_id, "small") for model_id in SMALL_MODELS)]
    if gpu_gib >= 70:
        model_plan.extend((model_id, "agent") for model_id in AGENT_MODELS)
    else:
        report["environment"]["agent_models_skipped"] = (
            "BF16 30B models require at least 70 GiB VRAM; this A100 has "
            f"{gpu_gib:.1f} GiB."
        )

    for model_id, role in model_plan:
        print(f"\n=== {model_id} ({role}) ===", flush=True)
        try:
            rows = (
                evaluate_small(model_id)
                if role == "small"
                else evaluate_agent(model_id)
            )
            report["models"][model_id] = {"role": role, "cases": rows}
            report["summary"][model_id] = summarize(rows)
        except Exception as exc:
            report["models"][model_id] = {
                "role": role,
                "error": f"{type(exc).__name__}: {exc}",
            }
            report["summary"][model_id] = {"error": str(exc)}
            gc.collect()
            torch.cuda.empty_cache()
        save_report(report)
        gc.collect()
        torch.cuda.empty_cache()
        shutil.rmtree(CACHE_ROOT, ignore_errors=True)
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)

    try:
        from google.colab import files

        files.download(str(RESULT_PATH))
    except ImportError:
        pass


if __name__ == "__main__":
    main()
