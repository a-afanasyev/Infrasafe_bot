#!/bin/bash
# Integration Service Load Test Runner
# UK Management Bot

set -e

echo "🚀 Integration Service Load Test Runner"
echo "========================================"
echo ""

# Configuration
HOST=${1:-"http://localhost:8009"}
USERS=${2:-1000}
SPAWN_RATE=${3:-20}
RUN_TIME=${4:-"17m"}
HEADLESS=${5:-"--headless"}

echo "Configuration:"
echo "  Host: $HOST"
echo "  Users: $USERS"
echo "  Spawn Rate: $SPAWN_RATE users/sec"
echo "  Run Time: $RUN_TIME"
echo "  Mode: $([ "$HEADLESS" == "--headless" ] && echo "Headless" || echo "Web UI")"
echo ""

# Check if Integration Service is running
echo "🔍 Checking if Integration Service is available..."
if ! curl -sf "$HOST/health" > /dev/null; then
    echo "❌ Integration Service is not accessible at $HOST"
    echo "Please start the service first:"
    echo "  cd ../../"
    echo "  docker-compose up -d integration-service"
    exit 1
fi
echo "✅ Integration Service is running"
echo ""

# Check if locust is installed
if ! command -v locust &> /dev/null; then
    echo "❌ Locust is not installed"
    echo "Install it with: pip install locust"
    exit 1
fi

# Create results directory
RESULTS_DIR="results/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"
echo "📁 Results will be saved to: $RESULTS_DIR"
echo ""

# Run load test
echo "🏃 Starting load test..."
echo "Press Ctrl+C to stop"
echo ""

if [ "$HEADLESS" == "--headless" ]; then
    # Headless mode with CSV output
    locust \
        -f locustfile.py \
        --host="$HOST" \
        --users="$USERS" \
        --spawn-rate="$SPAWN_RATE" \
        --run-time="$RUN_TIME" \
        --headless \
        --csv="$RESULTS_DIR/results" \
        --html="$RESULTS_DIR/report.html" \
        --logfile="$RESULTS_DIR/locust.log" \
        --loglevel=INFO
else
    # Web UI mode
    echo "Web UI will be available at: http://localhost:8089"
    locust \
        -f locustfile.py \
        --host="$HOST"
fi

# Print summary
if [ -f "$RESULTS_DIR/results_stats.csv" ]; then
    echo ""
    echo "📊 Test Results Summary:"
    echo "======================="
    echo ""
    tail -n 1 "$RESULTS_DIR/results_stats.csv" | awk -F',' '{
        printf "  Total Requests: %s\n", $3
        printf "  Failures: %s\n", $4
        printf "  Average Response Time: %s ms\n", $7
        printf "  Min Response Time: %s ms\n", $8
        printf "  Max Response Time: %s ms\n", $9
        printf "  P50: %s ms\n", $13
        printf "  P95: %s ms\n", $17
        printf "  P99: %s ms\n", $19
        printf "  Requests/sec: %s\n", $11
    }'
    echo ""
    echo "✅ Full report available at: $RESULTS_DIR/report.html"
fi

echo ""
echo "🏁 Load test completed!"
