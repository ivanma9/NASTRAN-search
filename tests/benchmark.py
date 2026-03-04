"""Quick benchmark: latency + relevance quality for LegacyLens API."""

import json
import time
import requests

API_BASE = "https://legacylens-production-bcaa.up.railway.app"

# Test queries with expected signals (unit names or keywords that should appear in results)
TEST_QUERIES = [
    # --- Original queries ---
    {
        "query": "What does the DCOMP subroutine do?",
        "expect_units": ["DCOMP", "DDCOMP"],
        "expect_files_contain": ["dcomp"],
        "type": "specific_unit",
    },
    {
        "query": "How does NASTRAN handle matrix decomposition?",
        "expect_units": ["DCOMP", "DDCOMP", "CDCOMP", "SDCMPS"],
        "expect_files_contain": ["dcomp", "cdcomp", "sdcmp"],
        "type": "conceptual",
    },
    {
        "query": "What subroutines reference COMMON block /SYSTEM/?",
        "expect_units": [],  # hard to predict, but should have results
        "expect_files_contain": [],
        "type": "dependency",
    },
    {
        "query": "How are stiffness matrices assembled?",
        "expect_units": [],
        "expect_files_contain": [],
        "type": "conceptual",
    },
    {
        "query": "What is the purpose of the XREAD subroutine?",
        "expect_units": ["XREAD"],
        "expect_files_contain": ["xread"],
        "type": "specific_unit",
    },
    {
        "query": "How does NASTRAN handle singular matrices?",
        "expect_units": [],
        "expect_files_contain": [],
        "type": "conceptual",
    },
    {
        "query": "What are the installation instructions?",
        "expect_units": [],
        "expect_files_contain": [],
        "type": "irrelevant",  # no code for this
    },
    {
        "query": "Explain the BANDIT module",
        "expect_units": ["BANDIT"],
        "expect_files_contain": ["bandit"],
        "type": "specific_unit",
    },
    # --- Scenario-based queries (adapted from COBOL testing scenarios) ---
    # Scenario 1: "Where is the main entry point of this program?"
    {
        "query": "Where is the main PROGRAM entry point in NASTRAN-95?",
        "expect_units": [],
        "expect_files_contain": [],
        "type": "entry_point",
    },
    # Scenario 2: "What functions modify the CUSTOMER-RECORD?" → COMMON block state
    {
        "query": "What subroutines modify COMMON block /ZZZZZZ/?",
        "expect_units": [],
        "expect_files_contain": [],
        "type": "dependency",
    },
    # Scenario 3: "Explain what the CALCULATE-INTEREST paragraph does" → specific unit
    {
        "query": "Explain what the DECOMP subroutine does",
        "expect_units": ["DECOMP"],
        "expect_files_contain": ["decomp"],
        "type": "specific_unit",
    },
    # Scenario 4: "Find all file I/O operations"
    {
        "query": "Find all file I/O operations and READ/WRITE statements",
        "expect_units": [],
        "expect_files_contain": [],
        "type": "conceptual",
    },
    # Scenario 5: "What are the dependencies of MODULE-X?"
    {
        "query": "What are the dependencies of the DCOMP subroutine?",
        "expect_units": ["DCOMP", "DDCOMP", "CDCOMP", "SDCOMP", "SDCOMPX"],
        "expect_files_contain": ["dcomp"],
        "type": "dependency",
    },
    # Scenario 6: "Show me error handling patterns in this codebase"
    {
        "query": "Show me error handling patterns in the NASTRAN-95 codebase",
        "expect_units": [],
        "expect_files_contain": [],
        "type": "conceptual",
    },
]


def run_benchmark():
    latencies = []
    results_summary = []

    print(f"{'Query':<50} {'Latency':>8} {'Chunks':>7} {'Avg Dist':>9} {'Hit?':>5}")
    print("=" * 85)

    for test in TEST_QUERIES:
        q = test["query"]
        start = time.time()
        try:
            resp = requests.post(
                f"{API_BASE}/api/ask",
                json={"question": q, "top_k": 5},
                timeout=60,
            )
            elapsed = time.time() - start
            latencies.append(elapsed)

            if resp.status_code != 200:
                print(f"{q:<50} {'ERROR':>8} {resp.status_code}")
                results_summary.append({"query": q, "hit": False, "latency": elapsed})
                continue

            data = resp.json()
            chunks = data.get("chunks", [])
            n_chunks = len(chunks)

            # Average distance (lower = more relevant)
            scores = [c.get("score", 0) for c in chunks]
            avg_score = sum(scores) / len(scores) if scores else 0

            # Check if expected units/files appear in results
            hit = False
            if test["expect_units"]:
                found_units = {c.get("unit_name", "").upper() for c in chunks}
                hit = bool(found_units & {u.upper() for u in test["expect_units"]})
            elif test["expect_files_contain"]:
                found_files = " ".join(c.get("file_path", "").lower() for c in chunks)
                hit = any(kw in found_files for kw in test["expect_files_contain"])
            elif test["type"] == "irrelevant":
                # For irrelevant queries, "hit" = all results have high distance (low relevance)
                hit = avg_score > 1.0  # Correctly identified as irrelevant
            else:
                # For conceptual queries without specific expectations, check we got results
                hit = n_chunks > 0 and avg_score < 1.0

            hit_str = "✓" if hit else "✗"
            print(f"{q:<50} {elapsed:>7.2f}s {n_chunks:>7} {avg_score:>9.3f} {hit_str:>5}")

            results_summary.append({
                "query": q,
                "type": test["type"],
                "latency": elapsed,
                "chunks": n_chunks,
                "avg_distance": avg_score,
                "min_distance": min(scores) if scores else 0,
                "max_distance": max(scores) if scores else 0,
                "hit": hit,
            })

        except Exception as e:
            elapsed = time.time() - start
            print(f"{q:<50} {'FAIL':>8} {e}")
            results_summary.append({"query": q, "hit": False, "latency": elapsed})

    # Summary
    print("\n" + "=" * 85)
    print("SUMMARY")
    print("=" * 85)

    if latencies:
        avg_lat = sum(latencies) / len(latencies)
        p50 = sorted(latencies)[len(latencies) // 2]
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        print(f"  Latency  — avg: {avg_lat:.2f}s, p50: {p50:.2f}s, p95: {p95:.2f}s")

    hits = sum(1 for r in results_summary if r.get("hit"))
    total = len(results_summary)
    print(f"  Accuracy — {hits}/{total} ({100*hits/total:.0f}%)")

    all_dists = [r["avg_distance"] for r in results_summary if "avg_distance" in r]
    if all_dists:
        print(f"  Avg distance — {sum(all_dists)/len(all_dists):.3f} (lower = more relevant)")

    # Per-type breakdown
    types = set(r.get("type", "") for r in results_summary)
    for t in sorted(types):
        type_results = [r for r in results_summary if r.get("type") == t]
        type_hits = sum(1 for r in type_results if r.get("hit"))
        type_dists = [r["avg_distance"] for r in type_results if "avg_distance" in r]
        avg_d = sum(type_dists) / len(type_dists) if type_dists else 0
        print(f"    {t:<20} — {type_hits}/{len(type_results)} hits, avg dist: {avg_d:.3f}")


if __name__ == "__main__":
    run_benchmark()
