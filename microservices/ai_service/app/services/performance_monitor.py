# Performance Monitoring and Metrics Collection
# UK Management Bot - AI Service Stage 4

import asyncio
import logging
import time
import psutil
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from statistics import mean, median

logger = logging.getLogger(__name__)


@dataclass
class MetricEntry:
    """Single metric entry"""
    timestamp: datetime
    value: float
    labels: Dict[str, str]


@dataclass
class PerformanceSnapshot:
    """System performance snapshot"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_mb: float
    disk_usage_percent: float
    active_connections: int
    request_rate: float
    error_rate: float


class MetricsCollector:
    """
    Comprehensive metrics collection system
    """

    def __init__(self, retention_hours: int = 24):
        self.retention_hours = retention_hours
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self.counters: Dict[str, int] = defaultdict(int)
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        self.gauges: Dict[str, float] = defaultdict(float)

        # Request tracking
        self.request_times: deque = deque(maxlen=1000)
        self.error_counts: deque = deque(maxlen=1000)

        # System monitoring
        self.system_snapshots: deque = deque(maxlen=1440)  # 24 hours of minute snapshots
        self._monitoring_active = False
        self._monitoring_thread = None

    def record_request_time(self, endpoint: str, duration_ms: float, status_code: int = 200):
        """Record request processing time"""
        now = datetime.now()

        self.metrics[f"request_duration_{endpoint}"].append(
            MetricEntry(now, duration_ms, {"endpoint": endpoint, "status": str(status_code)})
        )

        self.request_times.append((now, duration_ms))

        if status_code >= 400:
            self.error_counts.append((now, 1))
            self.increment_counter(f"errors_{endpoint}")

        self.increment_counter(f"requests_{endpoint}")

    def increment_counter(self, name: str, value: int = 1, labels: Optional[Dict[str, str]] = None):
        """Increment a counter metric"""
        self.counters[name] += value

        if labels:
            labeled_name = f"{name}_{self._labels_to_string(labels)}"
            self.counters[labeled_name] += value

    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Set a gauge metric"""
        self.gauges[name] = value

        if labels:
            labeled_name = f"{name}_{self._labels_to_string(labels)}"
            self.gauges[labeled_name] = value

    def record_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Record a value in histogram"""
        self.histograms[name].append(value)

        # Keep only recent values
        if len(self.histograms[name]) > 1000:
            self.histograms[name] = self.histograms[name][-500:]

        if labels:
            labeled_name = f"{name}_{self._labels_to_string(labels)}"
            self.histograms[labeled_name].append(value)

    def start_system_monitoring(self):
        """Start background system monitoring"""
        if self._monitoring_active:
            return

        self._monitoring_active = True
        self._monitoring_thread = threading.Thread(target=self._monitor_system, daemon=True)
        self._monitoring_thread.start()
        logger.info("System monitoring started")

    def stop_system_monitoring(self):
        """Stop background system monitoring"""
        self._monitoring_active = False
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=5)
        logger.info("System monitoring stopped")

    def _monitor_system(self):
        """Background system monitoring loop"""
        while self._monitoring_active:
            try:
                snapshot = self._take_system_snapshot()
                self.system_snapshots.append(snapshot)

                # Update gauges
                self.set_gauge("cpu_percent", snapshot.cpu_percent)
                self.set_gauge("memory_percent", snapshot.memory_percent)
                self.set_gauge("memory_mb", snapshot.memory_mb)
                self.set_gauge("disk_usage_percent", snapshot.disk_usage_percent)
                self.set_gauge("request_rate", snapshot.request_rate)
                self.set_gauge("error_rate", snapshot.error_rate)

                time.sleep(60)  # Take snapshot every minute

            except Exception as e:
                logger.error(f"System monitoring error: {e}")
                time.sleep(60)

    def _take_system_snapshot(self) -> PerformanceSnapshot:
        """Take current system performance snapshot"""
        now = datetime.now()

        # CPU and Memory
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # Network connections (approximate)
        try:
            connections = len(psutil.net_connections(kind='tcp'))
        except (psutil.AccessDenied, OSError):
            connections = 0

        # Request rate (requests per minute)
        minute_ago = now - timedelta(minutes=1)
        recent_requests = [
            t for t, _ in self.request_times
            if t >= minute_ago
        ]
        request_rate = len(recent_requests)

        # Error rate (errors per minute)
        recent_errors = [
            t for t, _ in self.error_counts
            if t >= minute_ago
        ]
        error_rate = len(recent_errors)

        return PerformanceSnapshot(
            timestamp=now,
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_mb=memory.used / (1024 * 1024),
            disk_usage_percent=disk.percent,
            active_connections=connections,
            request_rate=request_rate,
            error_rate=error_rate
        )

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get comprehensive metrics summary"""
        now = datetime.now()

        # Calculate request statistics
        recent_requests = [
            duration for timestamp, duration in self.request_times
            if timestamp >= now - timedelta(hours=1)
        ]

        request_stats = {}
        if recent_requests:
            request_stats = {
                "mean_ms": round(mean(recent_requests), 2),
                "median_ms": round(median(recent_requests), 2),
                "min_ms": round(min(recent_requests), 2),
                "max_ms": round(max(recent_requests), 2),
                "p95_ms": round(self._percentile(recent_requests, 95), 2),
                "p99_ms": round(self._percentile(recent_requests, 99), 2),
                "total_requests": len(recent_requests)
            }

        # System performance
        latest_snapshot = self.system_snapshots[-1] if self.system_snapshots else None
        system_performance = {}
        if latest_snapshot:
            system_performance = {
                "cpu_percent": latest_snapshot.cpu_percent,
                "memory_percent": latest_snapshot.memory_percent,
                "memory_mb": round(latest_snapshot.memory_mb, 2),
                "disk_usage_percent": latest_snapshot.disk_usage_percent,
                "active_connections": latest_snapshot.active_connections,
                "request_rate_per_minute": latest_snapshot.request_rate,
                "error_rate_per_minute": latest_snapshot.error_rate
            }

        # Top endpoints by request count
        endpoint_stats = {}
        for counter_name, count in self.counters.items():
            if counter_name.startswith("requests_"):
                endpoint = counter_name.replace("requests_", "")
                error_count = self.counters.get(f"errors_{endpoint}", 0)
                error_rate = (error_count / count * 100) if count > 0 else 0

                endpoint_stats[endpoint] = {
                    "total_requests": count,
                    "total_errors": error_count,
                    "error_rate_percent": round(error_rate, 2)
                }

        return {
            "timestamp": now.isoformat(),
            "request_statistics": request_stats,
            "system_performance": system_performance,
            "endpoint_statistics": endpoint_stats,
            "total_metrics_collected": sum(len(q) for q in self.metrics.values()),
            "monitoring_active": self._monitoring_active
        }

    def get_performance_trends(self, hours: int = 6) -> Dict[str, Any]:
        """Get performance trends over specified hours"""
        since = datetime.now() - timedelta(hours=hours)

        # Filter snapshots
        recent_snapshots = [
            s for s in self.system_snapshots
            if s.timestamp >= since
        ]

        if not recent_snapshots:
            return {"error": "No data available for the specified period"}

        # Calculate trends
        cpu_values = [s.cpu_percent for s in recent_snapshots]
        memory_values = [s.memory_percent for s in recent_snapshots]
        request_rates = [s.request_rate for s in recent_snapshots]
        error_rates = [s.error_rate for s in recent_snapshots]

        return {
            "period_hours": hours,
            "data_points": len(recent_snapshots),
            "cpu_trend": {
                "mean": round(mean(cpu_values), 2),
                "min": round(min(cpu_values), 2),
                "max": round(max(cpu_values), 2),
                "current": round(cpu_values[-1], 2) if cpu_values else 0
            },
            "memory_trend": {
                "mean": round(mean(memory_values), 2),
                "min": round(min(memory_values), 2),
                "max": round(max(memory_values), 2),
                "current": round(memory_values[-1], 2) if memory_values else 0
            },
            "request_rate_trend": {
                "mean": round(mean(request_rates), 2),
                "min": int(min(request_rates)),
                "max": int(max(request_rates)),
                "current": int(request_rates[-1]) if request_rates else 0
            },
            "error_rate_trend": {
                "mean": round(mean(error_rates), 2),
                "min": int(min(error_rates)),
                "max": int(max(error_rates)),
                "current": int(error_rates[-1]) if error_rates else 0
            }
        }

    def get_alert_conditions(self) -> List[Dict[str, Any]]:
        """Check for alert conditions"""
        alerts = []

        if not self.system_snapshots:
            return alerts

        latest = self.system_snapshots[-1]

        # High CPU usage
        if latest.cpu_percent > 80:
            alerts.append({
                "severity": "warning" if latest.cpu_percent < 90 else "critical",
                "condition": "high_cpu",
                "message": f"CPU usage at {latest.cpu_percent:.1f}%",
                "value": latest.cpu_percent,
                "threshold": 80
            })

        # High memory usage
        if latest.memory_percent > 85:
            alerts.append({
                "severity": "warning" if latest.memory_percent < 95 else "critical",
                "condition": "high_memory",
                "message": f"Memory usage at {latest.memory_percent:.1f}%",
                "value": latest.memory_percent,
                "threshold": 85
            })

        # High error rate
        if latest.error_rate > 10:  # More than 10 errors per minute
            alerts.append({
                "severity": "warning" if latest.error_rate < 30 else "critical",
                "condition": "high_error_rate",
                "message": f"Error rate at {latest.error_rate} errors/minute",
                "value": latest.error_rate,
                "threshold": 10
            })

        # Low request rate (possible service issue)
        if latest.request_rate == 0 and len(self.system_snapshots) > 5:
            # Check if we had requests before
            prev_rates = [s.request_rate for s in list(self.system_snapshots)[-5:-1]]
            if any(rate > 0 for rate in prev_rates):
                alerts.append({
                    "severity": "warning",
                    "condition": "no_requests",
                    "message": "No requests received in the last minute",
                    "value": 0,
                    "threshold": 1
                })

        return alerts

    def reset_metrics(self):
        """Reset all metrics"""
        self.metrics.clear()
        self.counters.clear()
        self.histograms.clear()
        self.gauges.clear()
        self.request_times.clear()
        self.error_counts.clear()
        logger.info("All metrics reset")

    @staticmethod
    def _percentile(data: List[float], percentile: int) -> float:
        """Calculate percentile of data"""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]

    @staticmethod
    def _labels_to_string(labels: Dict[str, str]) -> str:
        """Convert labels dict to string"""
        return "_".join(f"{k}_{v}" for k, v in sorted(labels.items()))


# Global metrics collector instance
metrics_collector = MetricsCollector()


def record_request_metrics(endpoint: str):
    """Decorator to automatically record request metrics"""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            status_code = 200

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status_code = 500
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                metrics_collector.record_request_time(endpoint, duration_ms, status_code)

        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            status_code = 200

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status_code = 500
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                metrics_collector.record_request_time(endpoint, duration_ms, status_code)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator