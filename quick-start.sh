#!/bin/bash
# Quick start script for tcp-bridge

set -e

echo "🚀 TCP Bridge Quick Start"
echo "=========================="

# Check if Docker is running
if ! docker info &> /dev/null; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

echo "✅ Docker is running"

# Check if make is available
if ! command -v make &> /dev/null; then
    echo "❌ Make is not available. Please install make."
    exit 1
fi

echo "✅ Make is available"

echo ""
echo "📋 Available options:"
echo "1. Build and run locally"
echo "2. Build Docker image"
echo "3. Start full stack (Docker Compose)"
echo "4. Start with monitoring (Docker Compose)"
echo "5. Show all available make targets"

read -p "Choose an option (1-5): " choice

case $choice in
    1)
        echo "🔨 Building locally..."
        make build-local
        echo "🎉 Build completed! Binary available at: ./bin/tcp-bridge"
        echo ""
        echo "🏃 To run:"
        echo "./bin/tcp-bridge -config config.yaml"
        ;;
    2)
        echo "🐳 Building Docker image..."
        make docker-build
        echo "🎉 Docker image built successfully!"
        echo ""
        echo "🏃 To run Docker container:"
        echo "make docker-run"
        ;;
    3)
        echo "📦 Starting full stack with Docker Compose..."
        docker-compose up -d
        echo "🎉 Services started!"
        echo ""
        echo "📊 Access points:"
        echo "- TCP Bridge metrics: http://localhost:8080/metrics"
        echo "- NATS monitoring: http://localhost:8222"
        echo ""
        echo "🛑 To stop: docker-compose down"
        ;;
    4)
        echo "📦 Starting with monitoring stack..."
        docker-compose --profile monitoring up -d
        echo "🎉 Services with monitoring started!"
        echo ""
        echo "📊 Access points:"
        echo "- TCP Bridge metrics: http://localhost:8080/metrics"
        echo "- NATS monitoring: http://localhost:8222"
        echo "- Prometheus: http://localhost:9090"
        echo "- Grafana: http://localhost:3000 (admin/admin)"
        echo ""
        echo "🛑 To stop: docker-compose down"
        ;;
    5)
        echo "📋 All available make targets:"
        make help
        ;;
    *)
        echo "❌ Invalid option. Please choose 1-5."
        exit 1
        ;;
esac

echo ""
echo "✅ Done!"