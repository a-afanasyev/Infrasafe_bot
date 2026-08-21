#!/usr/bin/env python3
"""Офлайн-оценка качества классификатора Group Intake на реальных сообщениях.

НЕ входит в CI: зовёт живой Anthropic API (нужен ANTHROPIC_API_KEY в env).
Гонять вручную перед rollout'ом и при смене модели/промпта/порога.

Формат входа — jsonl, по строке на анонимизированное сообщение:
    {"text": "...", "lang": "ru|uz", "kind": "residents|staff",
     "is_request": true, "category": "plumbing", "urgency": "high",
     "location_scope": "building", "address_expected": "дом 12"}
Обязательны text и is_request; остальные метки опциональны (метрика по полю
считается только по строкам, где метка проставлена).

Запуск:
    ANTHROPIC_API_KEY=... python3 scripts/group_intake_eval.py dataset.jsonl
    ... --model claude-sonnet-5          # A/B кандидат
    ... --threshold-sweep                # подбор GROUP_INTAKE_MIN_CONFIDENCE

Выводит по разрезам (all / ru / uz / residents / staff):
    request precision / recall / F1; category / urgency / location_scope
    accuracy (по размеченным строкам); p50/p95 latency; стоимость (по usage).
"""
import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Haiku 4.5: $1/$5 за MTok (для грубой оценки стоимости прогона).
PRICE_IN_PER_MTOK = 1.0
PRICE_OUT_PER_MTOK = 5.0


async def run(dataset_path: str, model: str | None, threshold_sweep: bool) -> int:
    from uk_management_bot.config.settings import settings
    from uk_management_bot.services.group_intake.classifier import (
        Outcome,
        classify_message,
    )

    if model:
        settings.GROUP_INTAKE_MODEL = model
    if not settings.ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY не задан", file=sys.stderr)
        return 2

    rows = []
    with open(dataset_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        print("пустой датасет", file=sys.stderr)
        return 2

    print(f"модель: {settings.GROUP_INTAKE_MODEL}, порог: "
          f"{settings.GROUP_INTAKE_MIN_CONFIDENCE}, строк: {len(rows)}")

    results = []
    latencies = []
    for i, row in enumerate(rows):
        t0 = time.monotonic()
        res = await classify_message(row["text"])
        latencies.append(time.monotonic() - t0)
        results.append(res)
        if (i + 1) % 20 == 0:
            print(f"  ...{i + 1}/{len(rows)}", file=sys.stderr)

    def slice_report(name: str, idxs: list[int]) -> None:
        if not idxs:
            return
        tp = fp = fn = tn = errors = 0
        cat_ok = cat_n = urg_ok = urg_n = scope_ok = scope_n = 0
        for i in idxs:
            row, res = rows[i], results[i]
            expected = bool(row["is_request"])
            if res.outcome is Outcome.PROCESSING_ERROR:
                errors += 1
                continue
            predicted = res.outcome is Outcome.REQUEST
            tp += predicted and expected
            fp += predicted and not expected
            fn += (not predicted) and expected
            tn += (not predicted) and (not expected)
            if predicted and expected:
                if row.get("category"):
                    cat_n += 1
                    cat_ok += res.category == row["category"]
                if row.get("urgency"):
                    urg_n += 1
                    urg_ok += res.urgency == row["urgency"]
                if row.get("location_scope"):
                    scope_n += 1
                    scope_ok += res.location_scope == row["location_scope"]
        prec = tp / (tp + fp) if (tp + fp) else float("nan")
        rec = tp / (tp + fn) if (tp + fn) else float("nan")
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else float("nan")
        print(f"[{name}] n={len(idxs)} err={errors} "
              f"P={prec:.2f} R={rec:.2f} F1={f1:.2f}"
              + (f" cat_acc={cat_ok / cat_n:.2f}({cat_n})" if cat_n else "")
              + (f" urg_acc={urg_ok / urg_n:.2f}({urg_n})" if urg_n else "")
              + (f" scope_acc={scope_ok / scope_n:.2f}({scope_n})" if scope_n else ""))

    slices: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(rows):
        slices["all"].append(i)
        if row.get("lang"):
            slices[row["lang"]].append(i)
        if row.get("kind"):
            slices[row["kind"]].append(i)
    for name in ("all", "ru", "uz", "residents", "staff"):
        slice_report(name, slices.get(name, []))

    lat_sorted = sorted(latencies)
    print(f"latency p50={statistics.median(lat_sorted):.2f}s "
          f"p95={lat_sorted[int(len(lat_sorted) * 0.95) - 1]:.2f}s")

    if threshold_sweep:
        print("\nthreshold sweep (эффект порога на уже полученных confidence):")
        for thr in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
            tp = fp = fn = 0
            for i, res in enumerate(results):
                if res.outcome is Outcome.PROCESSING_ERROR:
                    continue
                expected = bool(rows[i]["is_request"])
                predicted = (
                    res.outcome is Outcome.REQUEST and res.confidence >= thr
                ) or (
                    # NOT_REQUEST со снятым порогом не восстановить — считаем как есть
                    False
                )
                tp += predicted and expected
                fp += predicted and not expected
                fn += (not predicted) and expected
            prec = tp / (tp + fp) if (tp + fp) else float("nan")
            rec = tp / (tp + fn) if (tp + fn) else float("nan")
            print(f"  thr={thr:.1f}  P={prec:.2f} R={rec:.2f}")
        print("  (для честного sweep ниже текущего порога прогоните с "
              "GROUP_INTAKE_MIN_CONFIDENCE=0)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", help="jsonl с размеченными сообщениями")
    parser.add_argument("--model", default=None, help="переопределить модель (A/B)")
    parser.add_argument("--threshold-sweep", action="store_true")
    args = parser.parse_args()
    return asyncio.run(run(args.dataset, args.model, args.threshold_sweep))


if __name__ == "__main__":
    raise SystemExit(main())
