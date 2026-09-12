"""Small local read-load measurement; not a production scalability certification."""

import concurrent.futures
import json
import statistics
import time
from pathlib import Path

import httpx


def main():
    with httpx.Client(base_url="http://127.0.0.1:8787", timeout=20) as client:
        cases = client.get("/api/investigations").json()
        case_id = cases[0]["id"]
        paths = ["/api/metrics", "/api/investigations", f"/api/investigations/{case_id}"]

        def measure(index):
            start = time.perf_counter()
            response = client.get(paths[index % len(paths)])
            return (time.perf_counter() - start) * 1000, response.status_code

        start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(measure, range(120)))
        elapsed = time.perf_counter() - start
    values = sorted(r[0] for r in results)
    report = {
        "scope": "Local API reads only, four owned incidents, one server process. Excludes ingestion and model/runner throughput.",
        "requests": len(results),
        "concurrency": 8,
        "successes": sum(code == 200 for _, code in results),
        "p50_ms": round(statistics.median(values), 2),
        "p95_ms": round(values[int(len(values) * 0.95) - 1], 2),
        "requests_per_second": round(len(results) / elapsed, 2),
    }
    Path("var/load-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
