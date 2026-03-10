package main

import (
	"encoding/json"
	"fmt"
	"log"
	"time"

	"github.com/nats-io/nats.go"
)

// Request payload structure
type RequestPayload struct {
	MessageType string `json:"message_type"`
	RequestID   int    `json:"request_id"`
	Action      string `json:"action"`
	OrderID     int    `json:"order_id"`
	Timestamp   int64  `json:"timestamp"`
}

// Response payload structure
type ResponsePayload struct {
	RequestID   int         `json:"request_id"`
	Status      string      `json:"status"`
	Data        interface{} `json:"data"`
	Timestamp   int64       `json:"timestamp"`
	ProcessedBy string      `json:"processed_by"`
}

func main() {
	fmt.Println("=== NATS Service (TCP→NATS Simulator) ===")
	fmt.Println("This service receives requests from tcp-bridge via NATS")
	fmt.Println("And sends responses back")
	
	// Connect to NATS
	nc, err := nats.Connect("nats://localhost:4222")
	if err != nil {
		log.Fatalf("Failed to connect to NATS: %v", err)
	}
	defer nc.Close()
	
	fmt.Println("✅ Connected to NATS server")
	
	// Subscribe to order-related requests
	fmt.Println("📡 Subscribing to internal_req.order subject...")
	
	_, err = nc.Subscribe("internal_req.order", func(msg *nats.Msg) {
		fmt.Printf("\n📨 Received request from subject: %s\n", msg.Subject)
		fmt.Printf("   Reply-To: %s\n", msg.Reply)
		fmt.Printf("   Payload: %s\n", string(msg.Data))
		
		// Parse request
		var req RequestPayload
		if err := json.Unmarshal(msg.Data, &req); err != nil {
			fmt.Printf("❌ Failed to parse request: %v\n", err)
			return
		}
		
		// Simulate processing time
		time.Sleep(200 * time.Millisecond)
		
		// Create response payload based on action
		var responseData interface{}
		switch req.Action {
		case "get_order_status":
			responseData = map[string]interface{}{
				"order_id": req.OrderID,
				"status":   "shipped",
				"tracking": "TRK123456789",
				"items": []map[string]interface{}{
					{"name": "Widget A", "quantity": 2, "price": 19.99},
					{"name": "Widget B", "quantity": 1, "price": 29.99},
				},
				"total":        69.97,
				"shipping_date": time.Now().AddDate(0, 0, -2).Unix(),
				"delivery_date": time.Now().AddDate(0, 0, 1).Unix(),
			}
		default:
			responseData = map[string]interface{}{
				"message": "Unknown action: " + req.Action,
			}
		}
		
		response := ResponsePayload{
			RequestID:   req.RequestID,
			Status:      "success",
			Data:        responseData,
			Timestamp:   time.Now().Unix(),
			ProcessedBy: "nats-order-service",
		}
		
		// Convert to JSON
		responseBytes, err := json.Marshal(response)
		if err != nil {
			fmt.Printf("❌ Failed to marshal response: %v\n", err)
			return
		}
		
		// Send response
		if msg.Reply != "" {
			if err := msg.Respond(responseBytes); err != nil {
				fmt.Printf("❌ Failed to send response: %v\n", err)
				return
			}
			
			fmt.Printf("✅ Sent response: %s\n", string(responseBytes))
		} else {
			fmt.Println("⚠️  No reply subject provided")
		}
	})
	
	if err != nil {
		log.Fatalf("Failed to subscribe: %v", err)
	}
	
	// Also subscribe to other subjects for demo
	fmt.Println("📡 Subscribing to internal_req.* subjects...")
	
	_, err = nc.Subscribe("internal_req.*", func(msg *nats.Msg) {
		if msg.Subject == "internal_req.order" {
			return // Already handled above
		}
		
		fmt.Printf("\n📨 Received request from subject: %s\n", msg.Subject)
		fmt.Printf("   Reply-To: %s\n", msg.Reply)
		fmt.Printf("   Payload: %s\n", string(msg.Data))
		
		// Simple generic response for other subjects
		response := ResponsePayload{
			RequestID:   0,
			Status:      "success",
			Data: map[string]interface{}{
				"message":    "Processed by generic handler",
				"subject":    msg.Subject,
				"processed":  true,
			},
			Timestamp:   time.Now().Unix(),
			ProcessedBy: "nats-generic-service",
		}
		
		responseBytes, err := json.Marshal(response)
		if err != nil {
			fmt.Printf("❌ Failed to marshal response: %v\n", err)
			return
		}
		
		if msg.Reply != "" {
			msg.Respond(responseBytes)
			fmt.Printf("✅ Sent generic response: %s\n", string(responseBytes))
		}
	})
	
	if err != nil {
		log.Fatalf("Failed to subscribe to wildcard: %v", err)
	}
	
	fmt.Println("🎯 Ready to process requests!")
	fmt.Println("   - internal_req.order (specific handler)")
	fmt.Println("   - internal_req.* (generic handler)")
	
	// Keep the service running
	select {}
}