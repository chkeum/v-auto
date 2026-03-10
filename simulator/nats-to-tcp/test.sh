#!/bin/bash
# Test script for NATS→TCP scenario

echo "🚀 Starting NATS→TCP Test Scenario"
echo "=================================="

# Check if NATS is running
echo "🔍 Checking NATS server..."
if ! nc -z localhost 4222; then
    echo "❌ NATS server not running on port 4222"
    echo "💡 Start NATS server first:"
    echo "   docker run -d --name nats-server -p 4222:4222 -p 8222:8222 nats:latest --http_port 8222"
    exit 1
fi
echo "✅ NATS server is running"

# Check if tcp-bridge is running
echo "🔍 Checking tcp-bridge..."
if ! nc -z localhost 8000; then
    echo "❌ tcp-bridge not running on port 8000"  
    echo "💡 Start tcp-bridge first:"
    echo "   cd /home/bigwo/nTels/07.UPM/github/tcp_bridge && ./tcp-bridge -config config.yaml"
    exit 1
fi
echo "✅ tcp-bridge is running"

echo ""
echo "🎯 Test Scenario: NATS→TCP"
echo "   1. NATS Client sends requests to 'external_req' subject"
echo "   2. tcp-bridge forwards them to TCP Server on port 8000"  
echo "   3. TCP Server processes and responds"
echo "   4. Response flows back: TCP Server → tcp-bridge → NATS Client"
echo ""

echo "📋 Starting components..."
echo "   Starting TCP Server (background)..."

# Start TCP Server in background
cd "$(dirname "$0")"
go run tcp-server.go &
TCP_SERVER_PID=$!

# Wait a bit for server to start
sleep 2

echo "✅ TCP Server started (PID: $TCP_SERVER_PID)"
echo ""
echo "🚀 Starting NATS Client (foreground)..."
echo "   Press Ctrl+C to stop the test"
echo ""

# Start NATS Client in foreground
go run nats-client.go

# Cleanup on exit
echo ""
echo "🧹 Cleaning up..."
kill $TCP_SERVER_PID 2>/dev/null
echo "✅ Test completed"