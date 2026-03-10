package queue

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"tcp-bridge/internal/config"
)

// SendQueue manages the bounded send queue for TCP frames
type SendQueue struct {
	logger *slog.Logger
	config *config.QueueConfig
	
	// Queue
	queue       chan *config.SendJob
	maxSize     int
	sendTimeout time.Duration
	
	// Metrics
	enqueueCount int64
	dequeueCount int64
	dropCount    int64
}

// NewSendQueue creates a new send queue
func NewSendQueue(logger *slog.Logger, cfg *config.QueueConfig) *SendQueue {
	return &SendQueue{
		logger:      logger,
		config:      cfg,
		queue:       make(chan *config.SendJob, cfg.SendQueueSize),
		maxSize:     cfg.SendQueueSize,
		sendTimeout: cfg.SendTimeout,
	}
}

// Start starts the send queue (no-op for now, queue is ready immediately)
func (sq *SendQueue) Start(ctx context.Context) error {
	sq.logger.Info("send queue started", "max_size", sq.maxSize)
	return nil
}

// Stop stops the send queue
func (sq *SendQueue) Stop() {
	sq.logger.Info("stopping send queue")
	
	// Close the queue
	close(sq.queue)
	
	// Log final statistics
	sq.logger.Info("send queue stopped",
		"enqueued", sq.enqueueCount,
		"dequeued", sq.dequeueCount,
		"dropped", sq.dropCount)
}

// Enqueue adds a send job to the queue
func (sq *SendQueue) Enqueue(job *config.SendJob) error {
	return sq.EnqueueWithTimeout(job, sq.sendTimeout)
}

// EnqueueWithTimeout adds a send job to the queue with a custom timeout
func (sq *SendQueue) EnqueueWithTimeout(job *config.SendJob, timeout time.Duration) error {
	select {
	case sq.queue <- job:
		sq.enqueueCount++
		sq.logger.Debug("job enqueued",
			"tid", job.TID,
			"frame_type", job.Frame.Type,
			"target", job.TargetHint,
			"queue_size", len(sq.queue))
		return nil
		
	case <-time.After(timeout):
		sq.dropCount++
		sq.logger.Warn("job dropped due to timeout",
			"tid", job.TID,
			"frame_type", job.Frame.Type,
			"target", job.TargetHint,
			"timeout", timeout)
		return fmt.Errorf("queue enqueue timeout after %v", timeout)
	}
}

// TryEnqueue attempts to add a send job to the queue without blocking
func (sq *SendQueue) TryEnqueue(job *config.SendJob) error {
	select {
	case sq.queue <- job:
		sq.enqueueCount++
		sq.logger.Debug("job enqueued (non-blocking)",
			"tid", job.TID,
			"frame_type", job.Frame.Type,
			"target", job.TargetHint,
			"queue_size", len(sq.queue))
		return nil
		
	default:
		sq.dropCount++
		sq.logger.Warn("job dropped due to full queue",
			"tid", job.TID,
			"frame_type", job.Frame.Type,
			"target", job.TargetHint,
			"queue_size", len(sq.queue))
		return fmt.Errorf("queue is full")
	}
}

// Dequeue removes and returns a send job from the queue
// This method blocks until a job is available or context is cancelled
func (sq *SendQueue) Dequeue(ctx context.Context) (*config.SendJob, error) {
	select {
	case job := <-sq.queue:
		if job == nil {
			return nil, fmt.Errorf("queue closed")
		}
		sq.dequeueCount++
		sq.logger.Debug("job dequeued",
			"tid", job.TID,
			"frame_type", job.Frame.Type,
			"target", job.TargetHint,
			"queue_size", len(sq.queue))
		return job, nil
		
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}

// GetChannel returns the underlying channel for direct access by sender
func (sq *SendQueue) GetChannel() <-chan *config.SendJob {
	return sq.queue
}

// Size returns the current queue size
func (sq *SendQueue) Size() int {
	return len(sq.queue)
}

// Capacity returns the maximum queue capacity
func (sq *SendQueue) Capacity() int {
	return sq.maxSize
}

// Stats returns queue statistics
func (sq *SendQueue) Stats() QueueStats {
	return QueueStats{
		Size:         len(sq.queue),
		Capacity:     sq.maxSize,
		EnqueueCount: sq.enqueueCount,
		DequeueCount: sq.dequeueCount,
		DropCount:    sq.dropCount,
	}
}

// QueueStats represents queue statistics
type QueueStats struct {
	Size         int   `json:"size"`
	Capacity     int   `json:"capacity"`
	EnqueueCount int64 `json:"enqueue_count"`
	DequeueCount int64 `json:"dequeue_count"`
	DropCount    int64 `json:"drop_count"`
}

// IsFull returns true if the queue is full
func (sq *SendQueue) IsFull() bool {
	return len(sq.queue) >= sq.maxSize
}

// IsEmpty returns true if the queue is empty
func (sq *SendQueue) IsEmpty() bool {
	return len(sq.queue) == 0
}

// UtilizationPercent returns the queue utilization as a percentage (0-100)
func (sq *SendQueue) UtilizationPercent() float64 {
	if sq.maxSize == 0 {
		return 0
	}
	return float64(len(sq.queue)) / float64(sq.maxSize) * 100
}