"""
Integration Service - Load Testing with Locust
UK Management Bot

Load test scenarios for Integration Service endpoints.

Run:
    locust -f tests/load/locustfile.py --host=http://localhost:8009

Targets:
    - 1000 concurrent users
    - 1000 requests/second sustained
    - P95 response time < 200ms
    - Error rate < 0.1%
"""

import json
import random
import hashlib
import hmac
from datetime import datetime
from typing import Dict, Any
from locust import HttpUser, task, between, events


class IntegrationServiceUser(HttpUser):
    """
    Locust user simulating Integration Service usage.

    Task distribution:
    - 50% Health checks (lightweight)
    - 20% Webhook events (medium)
    - 15% Cache operations (lightweight)
    - 10% Google Sheets operations (heavy)
    - 5% Event publishing (medium)
    """

    wait_time = between(0.1, 0.5)  # Wait 100-500ms between tasks
    host = "http://localhost:8009"

    def on_start(self):
        """Initialize user session"""
        self.tenant_id = f"tenant_{random.randint(1, 10)}"
        self.webhook_secret = "test_secret_key_123"

    @task(50)
    def health_check(self):
        """Test basic health check endpoint (50% of requests)"""
        with self.client.get(
            "/health",
            name="/health [Health Check]",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    response.success()
                else:
                    response.failure(f"Unhealthy status: {data.get('status')}")
            else:
                response.failure(f"Got {response.status_code}")

    @task(20)
    def webhook_stripe(self):
        """Test Stripe webhook endpoint (20% of requests)"""
        # Generate realistic Stripe webhook payload
        event_id = f"evt_{random.randint(100000, 999999)}"
        payload = {
            "id": event_id,
            "object": "event",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": f"pi_{random.randint(100000, 999999)}",
                    "amount": random.randint(1000, 50000),
                    "currency": "usd",
                    "status": "succeeded"
                }
            },
            "created": int(datetime.utcnow().timestamp())
        }

        # Generate HMAC signature
        payload_str = json.dumps(payload, separators=(',', ':'))
        signature = hmac.new(
            self.webhook_secret.encode(),
            payload_str.encode(),
            hashlib.sha256
        ).hexdigest()

        with self.client.post(
            "/api/v1/webhooks/stripe",
            json=payload,
            headers={"X-Stripe-Signature": signature},
            name="/api/v1/webhooks/stripe [Webhook]",
            catch_response=True
        ) as response:
            if response.status_code in [200, 202]:
                response.success()
            else:
                response.failure(f"Got {response.status_code}")

    @task(15)
    def cache_stats(self):
        """Test cache statistics endpoint (15% of requests)"""
        with self.client.get(
            f"/cache/stats?tenant_id={self.tenant_id}",
            name="/cache/stats [Cache Stats]",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "namespaces" in data:
                    response.success()
                else:
                    response.failure("Missing namespaces in response")
            else:
                response.failure(f"Got {response.status_code}")

    @task(10)
    def google_sheets_health(self):
        """Test Google Sheets health endpoint (10% of requests)"""
        with self.client.get(
            "/api/v1/google-sheets/health",
            name="/api/v1/google-sheets/health [Sheets Health]",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got {response.status_code}")

    @task(5)
    def webhook_generic(self):
        """Test generic webhook endpoint (5% of requests)"""
        source = random.choice(["yandex_maps", "google_maps", "custom_service"])
        payload = {
            "event_id": f"gen_{random.randint(100000, 999999)}",
            "event_type": "data.updated",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "key": f"value_{random.randint(1, 100)}",
                "count": random.randint(1, 1000)
            }
        }

        with self.client.post(
            f"/api/v1/webhooks/generic/{source}",
            json=payload,
            name="/api/v1/webhooks/generic/{source} [Generic Webhook]",
            catch_response=True
        ) as response:
            if response.status_code in [200, 202]:
                response.success()
            else:
                response.failure(f"Got {response.status_code}")


class AdminUser(HttpUser):
    """
    Admin user performing monitoring and management tasks.

    Less frequent, more comprehensive checks.
    """

    wait_time = between(5, 10)  # Wait 5-10 seconds between tasks
    host = "http://localhost:8009"
    weight = 1  # 1 admin for every 10 regular users

    @task(40)
    def detailed_health_check(self):
        """Check detailed health status"""
        with self.client.get(
            "/health/detailed",
            name="/health/detailed [Admin Health]",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "dependencies" in data:
                    response.success()
                else:
                    response.failure("Missing dependencies in response")
            else:
                response.failure(f"Got {response.status_code}")

    @task(30)
    def get_metrics(self):
        """Fetch Prometheus metrics"""
        with self.client.get(
            "/metrics",
            name="/metrics [Admin Metrics]",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got {response.status_code}")

    @task(20)
    def get_all_cache_stats(self):
        """Get comprehensive cache statistics"""
        with self.client.get(
            "/cache/stats",
            name="/cache/stats [Admin Cache]",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got {response.status_code}")

    @task(10)
    def api_docs(self):
        """Access API documentation"""
        with self.client.get(
            "/docs",
            name="/docs [Admin Docs]",
            catch_response=True
        ) as response:
            if response.status_code in [200, 404]:  # 404 in production
                response.success()
            else:
                response.failure(f"Got {response.status_code}")


# Event listeners for statistics
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts"""
    print("\n" + "="*80)
    print("🚀 Integration Service Load Test Starting")
    print("="*80)
    print(f"Host: {environment.host}")
    print(f"Target: 1000 concurrent users, 1000 req/s sustained")
    print(f"Targets: P95 < 200ms, Error rate < 0.1%")
    print("="*80 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops"""
    print("\n" + "="*80)
    print("🏁 Integration Service Load Test Completed")
    print("="*80)

    stats = environment.stats
    print(f"\n📊 Summary Statistics:")
    print(f"  Total Requests: {stats.total.num_requests}")
    print(f"  Total Failures: {stats.total.num_failures}")
    print(f"  Failure Rate: {stats.total.fail_ratio * 100:.2f}%")
    print(f"  RPS: {stats.total.total_rps:.2f}")
    print(f"  Avg Response Time: {stats.total.avg_response_time:.0f}ms")
    print(f"  P50: {stats.total.get_response_time_percentile(0.50):.0f}ms")
    print(f"  P95: {stats.total.get_response_time_percentile(0.95):.0f}ms")
    print(f"  P99: {stats.total.get_response_time_percentile(0.99):.0f}ms")
    print(f"  Max Response Time: {stats.total.max_response_time:.0f}ms")

    # Check if targets were met
    print(f"\n✅ Target Achievement:")
    p95 = stats.total.get_response_time_percentile(0.95)
    error_rate = stats.total.fail_ratio * 100

    p95_met = p95 < 200
    error_met = error_rate < 0.1

    print(f"  P95 < 200ms: {'✅ PASS' if p95_met else '❌ FAIL'} ({p95:.0f}ms)")
    print(f"  Error rate < 0.1%: {'✅ PASS' if error_met else '❌ FAIL'} ({error_rate:.2f}%)")

    print("="*80 + "\n")


# Custom shape for load test scenarios
from locust import LoadTestShape

class StepLoadShape(LoadTestShape):
    """
    Step load pattern:
    - Ramp up to 1000 users over 5 minutes
    - Sustain 1000 users for 10 minutes
    - Ramp down over 2 minutes
    """

    step_time = 30  # seconds per step
    step_load = 100  # users per step
    spawn_rate = 20  # users per second
    time_limit = 1020  # 17 minutes total

    def tick(self):
        run_time = self.get_run_time()

        if run_time > self.time_limit:
            return None  # Stop test

        # Ramp up phase (0-5 minutes)
        if run_time < 300:
            user_count = round(run_time / self.step_time) * self.step_load
            return (min(user_count, 1000), self.spawn_rate)

        # Sustain phase (5-15 minutes)
        elif run_time < 900:
            return (1000, self.spawn_rate)

        # Ramp down phase (15-17 minutes)
        else:
            remaining_time = self.time_limit - run_time
            user_count = round(remaining_time / self.step_time) * self.step_load
            return (max(user_count, 0), self.spawn_rate)
