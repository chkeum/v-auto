#!/bin/bash

echo "=== TCP→NATS Flow Test ==="
echo ""
echo "Architecture:"
echo "  TCP Server (port 8000) ← tcp-bridge (client) → NATS → NATS Service"
echo ""
echo "Flow:"
echo "  1. tcp-bridge connects to TCP Server as client"
echo "  2. TCP Server sends REQUEST frames"
echo "  3. tcp-bridge forwards to NATS (internal_req.order)"
echo "  4. NATS Service responds"
echo "  5. tcp-bridge sends RESPONSE frames back"
echo "  6. TCP Server receives responses"
echo ""
echo "Starting components..."
echo ""

# Kill any existing processes
pkill -f tcp-server
pkill -f nats-service

# Build executables
echo "📦 Building TCP Server..."
go build -o tcp-server tcp-server.go

echo "📦 Building NATS Service..."
go build -o nats-service nats-service.go

# Start NATS Service (subscriber)
echo ""
echo "🚀 Starting NATS Service (subscribes to internal_req.order)..."
./nats-service &
NATS_PID=$!
sleep 2

# Start TCP Server (waits for tcp-bridge connection)
echo ""
echo "🚀 Starting TCP Server (listens on :8000)..."
echo "   ⚙️  Using flags: -send-requests -request-interval=200ms"
./tcp-server -send-requests &
TCP_PID=$!
sleep 2

echo ""
echo "✅ All components started!"
echo ""
echo "📋 Component Status:"
echo "   - NATS Service: PID $NATS_PID (subscribing to internal_req.order)"
echo "   - TCP Server:   PID $TCP_PID (listening on :8000)"
echo ""
echo "⚠️  Now start tcp-bridge separately:"
echo "   cd ../../"
echo "   ./bin/tcp-bridge config.yaml"
echo ""
echo "Press Ctrl+C to stop all components..."

# Wait for interrupt
trap "echo ''; echo 'Stopping...'; kill $NATS_PID $TCP_PID 2>/dev/null; exit 0" INT TERM

wait

# Cleanup on exit
echo ""
echo "🧹 Cleaning up..."
kill $NATS_SERVICE_PID 2>/dev/null
echo "✅ Test completed"