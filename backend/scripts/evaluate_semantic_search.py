#!/usr/bin/env python3
"""Evaluate a manually judged Arabic semantic-retrieval set."""
from __future__ import annotations

import argparse
import json
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from app.services.semantic_search import semantic_search  # noqa: E402


def reciprocal_rank(returned: list[str], relevant: set[str]) -> float:
    for rank, item in enumerate(returned, start=1):
        if item in relevant:
            return 1.0 / rank
    return 0.0


def evaluate(items: list[dict], k: int = 5) -> dict:
    recall, precision, rr = [], [], []
    primary_presence = []
    incorrect_topic = []
    semantic_false_positives = []
    details = []
    for case in items:
        rows = semantic_search(
            case["query"], limit=k,
            book_ids=case.get("book_ids"),
            qasida_number=case.get("qasida_number"),
        )
        returned = [row["match_id"] for row in rows]
        relevant = set(case["relevant_chunks"])
        found = relevant.intersection(returned)
        recall.append(len(found) / len(relevant) if relevant else 0.0)
        precision.append(len(found) / k)
        rr.append(reciprocal_rank(returned, relevant))
        primary_presence.append(any(row["source_code"] == "primary" for row in rows))
        forbidden = set(case.get("irrelevant_chunks", []))
        incorrect_topic.append(bool(forbidden.intersection(returned)))
        semantic_false_positives.append(sum(
            row["match_type"] == "semantic" and row["match_id"] not in relevant
            for row in rows
        ))
        details.append({
            "query": case["query"], "returned": returned,
            "relevant_found": sorted(found),
        })
    count = max(1, len(items))
    return {
        f"recall@{k}": sum(recall) / count,
        f"precision@{k}": sum(precision) / count,
        "mean_reciprocal_rank": sum(rr) / count,
        "primary_source_presence": sum(primary_presence) / count,
        "incorrect_topic_rate": sum(incorrect_topic) / count,
        "semantic_only_false_positives_per_query": sum(semantic_false_positives) / count,
        "query_count": len(items),
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "judgments", nargs="?",
        default=os.path.join(ROOT, "tests", "data", "arabic_retrieval_judgments.json"),
    )
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    with open(args.judgments, encoding="utf-8") as handle:
        items = json.load(handle)
    if not 30 <= len(items) <= 50:
        raise SystemExit("judgment set must contain 30-50 queries")
    print(json.dumps(evaluate(items, max(1, args.k)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
