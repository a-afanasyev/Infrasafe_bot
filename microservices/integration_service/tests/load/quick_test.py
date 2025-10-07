#!/usr/bin/env python3
"""
Quick performance test for Integration Service
Tests basic endpoints and measures response times
"""

import asyncio
import time
import statistics
from typing import List, Dict
import httpx


HOST = "http://localhost:8009"


async def test_endpoint(client: httpx.AsyncClient, url: str, name: str) -> Dict:
    """Test a single endpoint and return timing stats"""
    times = []
    errors = 0

    for _ in range(100):
        start = time.time()
        try:
            response = await client.get(url)
            duration_ms = (time.time() - start) * 1000
            times.append(duration_ms)

            if response.status_code not in [200, 404]:  # 404 ok for docs in prod
                errors += 1
        except Exception as e:
            errors += 1
            print(f"Error: {e}")

    if not times:
        return {"name": name, "error": "No successful requests"}

    return {
        "name": name,
        "count": len(times),
        "errors": errors,
        "avg_ms": round(statistics.mean(times), 2),
        "min_ms": round(min(times), 2),
        "max_ms": round(max(times), 2),
        "p50_ms": round(statistics.median(times), 2),
        "p95_ms": round(statistics.quantiles(times, n=20)[18], 2),
        "p99_ms": round(statistics.quantiles(times, n=100)[98], 2),
    }


async def test_concurrent_requests(concurrency: int = 10):
    """Test concurrent requests"""
    print(f"\n🔥 Testing {concurrency} concurrent requests...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        start = time.time()

        tasks = []
        for _ in range(concurrency):
            tasks.append(client.get(f"{HOST}/health"))

        responses = await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.time() - start

        errors = sum(1 for r in responses if isinstance(r, Exception) or r.status_code != 200)
        success = len(responses) - errors

        print(f"  ✅ Success: {success}/{len(responses)}")
        print(f"  ❌ Errors: {errors}")
        print(f"  ⏱️  Total time: {duration:.2f}s")
        print(f"  📊 RPS: {len(responses)/duration:.2f}")


async def main():
    print("="*80)
    print("🚀 Integration Service - Quick Performance Test")
    print("="*80)

    endpoints = [
        ("/health", "Health Check"),
        ("/health/detailed", "Detailed Health"),
        ("/cache/stats", "Cache Stats"),
        ("/api/v1/webhooks/health", "Webhook Health"),
        ("/api/v1/google-sheets/health", "Sheets Health"),
    ]

    print("\n📊 Sequential Test (100 requests per endpoint):")
    print("-" * 80)

    async with httpx.AsyncClient(timeout=30.0) as client:
        results = []
        for url, name in endpoints:
            print(f"\nTesting: {name} ({url})")
            result = await test_endpoint(client, f"{HOST}{url}", name)
            results.append(result)

            if "error" in result:
                print(f"  ❌ {result['error']}")
            else:
                print(f"  ✅ Avg: {result['avg_ms']}ms | P50: {result['p50_ms']}ms | P95: {result['p95_ms']}ms | P99: {result['p99_ms']}ms")
                print(f"  📈 Min: {result['min_ms']}ms | Max: {result['max_ms']}ms | Errors: {result['errors']}")

    # Test concurrent requests
    await test_concurrent_requests(10)
    await test_concurrent_requests(50)
    await test_concurrent_requests(100)

    print("\n" + "="*80)
    print("📋 Summary:")
    print("="*80)

    for result in results:
        if "error" not in result:
            status = "✅ PASS" if result['p95_ms'] < 200 else "⚠️  SLOW"
            print(f"{status} {result['name']:30s} P95: {result['p95_ms']:6.2f}ms | Avg: {result['avg_ms']:6.2f}ms")

    print("\n🎯 Performance Targets:")
    fast_endpoints = sum(1 for r in results if "error" not in r and r['p95_ms'] < 200)
    print(f"  Fast endpoints (P95 < 200ms): {fast_endpoints}/{len(results)}")

    avg_p95 = statistics.mean([r['p95_ms'] for r in results if "error" not in r])
    print(f"  Average P95: {avg_p95:.2f}ms")

    print("\n✨ Done!")


if __name__ == "__main__":
    asyncio.run(main())
