# Makefile for tcp-bridge
.PHONY: build test clean run docker-build docker-run lint fmt deps install help

# Variables
APP_NAME := tcp-bridge
VERSION := $(shell git describe --tags --abbrev=0 2>/dev/null || echo "v0.1.0")
BUILD_TIME := $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_COMMIT := $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
GO_VERSION := $(shell go version | awk '{print $$3}')

# Build flags
LDFLAGS := -ldflags "-X main.version=$(VERSION) -X main.buildTime=$(BUILD_TIME) -X main.gitCommit=$(GIT_COMMIT) -w -s"
BUILD_DIR := ./bin
DOCKER_IMAGE := tcp-bridge
DOCKER_TAG := $(VERSION)

# Default target
help: ## Show this help message
	@echo "Available targets:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Build targets
build: ## Build the application binary
	@echo "Building $(APP_NAME) $(VERSION)..."
	@mkdir -p $(BUILD_DIR)
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build $(LDFLAGS) -o $(BUILD_DIR)/$(APP_NAME) ./cmd/$(APP_NAME)
	@echo "Build completed: $(BUILD_DIR)/$(APP_NAME)"

build-local: ## Build for local development (current OS/arch)
	@echo "Building $(APP_NAME) for local development..."
	@mkdir -p $(BUILD_DIR)
	go build $(LDFLAGS) -o $(BUILD_DIR)/$(APP_NAME) ./cmd/$(APP_NAME)
	@echo "Local build completed: $(BUILD_DIR)/$(APP_NAME)"

# Test targets
test: ## Run all tests
	@echo "Running tests..."
	go test -v -race -coverprofile=coverage.out ./...
	@echo "Tests completed"

test-coverage: ## Run tests with coverage report
	@echo "Running tests with coverage..."
	go test -v -race -coverprofile=coverage.out ./...
	go tool cover -html=coverage.out -o coverage.html
	@echo "Coverage report generated: coverage.html"

benchmark: ## Run benchmarks
	@echo "Running benchmarks..."
	go test -bench=. -benchmem ./...

# Development targets
run: build-local ## Build and run the application locally
	@echo "Starting $(APP_NAME)..."
	./$(BUILD_DIR)/$(APP_NAME) -config config.yaml

run-dev: ## Run with go run for development
	@echo "Running $(APP_NAME) in development mode..."
	go run ./cmd/$(APP_NAME) -config config.yaml

# Code quality targets
fmt: ## Format Go code
	@echo "Formatting code..."
	go fmt ./...
	goimports -w .

lint: ## Run linter
	@echo "Running linter..."
	@if command -v golangci-lint >/dev/null 2>&1; then \
		golangci-lint run; \
	else \
		echo "golangci-lint not found. Install with: go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest"; \
		go vet ./...; \
	fi

# Dependency management
deps: ## Download and tidy dependencies
	@echo "Managing dependencies..."
	go mod download
	go mod tidy
	go mod verify

deps-update: ## Update all dependencies
	@echo "Updating dependencies..."
	go get -u ./...
	go mod tidy

# Docker targets
docker-build: ## Build Docker image
	@echo "Building Docker image $(DOCKER_IMAGE):$(DOCKER_TAG)..."
	docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) -t $(DOCKER_IMAGE):latest .
	@echo "Docker image built: $(DOCKER_IMAGE):$(DOCKER_TAG)"

docker-run: ## Run application in Docker container
	@echo "Running $(DOCKER_IMAGE) in Docker..."
	docker run --rm -it \
		-p 8080:8080 \
		-v $(PWD)/config.yaml:/app/config.yaml:ro \
		$(DOCKER_IMAGE):$(DOCKER_TAG)

# Installation targets  
install: build ## Install binary to system
	@echo "Installing $(APP_NAME) to /usr/local/bin..."
	sudo cp $(BUILD_DIR)/$(APP_NAME) /usr/local/bin/
	@echo "Installation completed"

# Cleanup targets
clean: ## Clean build artifacts
	@echo "Cleaning build artifacts..."
	rm -rf $(BUILD_DIR)
	rm -f coverage.out coverage.html
	docker image prune -f
	@echo "Cleanup completed"

clean-all: clean ## Clean everything including Docker images
	@echo "Cleaning all Docker images..."
	-docker rmi $(DOCKER_IMAGE):$(DOCKER_TAG) $(DOCKER_IMAGE):latest
	docker system prune -f

# Release targets
release: clean test build docker-build ## Build release (clean, test, build, docker)
	@echo "Release build completed for version $(VERSION)"

# Info targets
info: ## Show build information
	@echo "Project: $(APP_NAME)"
	@echo "Version: $(VERSION)"
	@echo "Build Time: $(BUILD_TIME)"
	@echo "Git Commit: $(GIT_COMMIT)"
	@echo "Go Version: $(GO_VERSION)"

# Generate targets
generate: ## Run go generate
	@echo "Running go generate..."
	go generate ./...

# Security targets
security: ## Run security checks
	@echo "Running security checks..."
	@if command -v gosec >/dev/null 2>&1; then \
		gosec ./...; \
	else \
		echo "gosec not found. Install with: go install github.com/securecodewarrior/gosec/v2/cmd/gosec@latest"; \
	fi

# Vendor targets (if using vendor)
vendor: ## Create vendor directory
	@echo "Creating vendor directory..."
	go mod vendor

vendor-clean: ## Remove vendor directory
	@echo "Removing vendor directory..."
	rm -rf vendor/