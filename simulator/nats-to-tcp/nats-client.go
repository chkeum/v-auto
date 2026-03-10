package main

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/nats-io/nats.go"
)

func main() {
	fmt.Println("=== NATS Client (NATS→TCP Simulator) ===")
	fmt.Println("This client sends requests to external_req subject")
	fmt.Println("The tcp-bridge will forward them to TCP server")
	
	// Connect to NATS
	nc, err := nats.Connect("nats://localhost:4222")
	if err != nil {
		log.Fatalf("Failed to connect to NATS: %v", err)
	}
	defer nc.Close()
	
	fmt.Println("✅ Connected to NATS server")
	
	requestID := 1
	
	for {
		// Create request message with msg_type (hex string for Message Type)
		// msg_type "05" = Subs-Change-Request (0x05)
		requestData := fmt.Sprintf(`{
			"msg_type": "05",
			"message_type": "user",
			"request_id": %d,
			"action": "get_profile", 
			"user_id": 12345,
			"timestamp": %d
		}`, requestID, time.Now().Unix())
		
		fmt.Printf("\n🚀 Sending NATS request #%d (external_req)\n", requestID)
		fmt.Printf("   Payload: %s\n", requestData)
		fmt.Printf("   Note: msg_type=05 (Subs-Change-Request)\n")
		
		// Send request with reply subject (RPC style) - 50초 timeout
		ctx, cancel := context.WithTimeout(context.Background(), 500*time.Second)
		
		msg, err := nc.RequestWithContext(ctx, "external_req", []byte(requestData))
		cancel()
		
		if err != nil {
			fmt.Printf("❌ Request #%d timeout/failed: %v\n", requestID, err)
			fmt.Printf("⏭️  Moving to next message...\n")
		} else {
			fmt.Printf("✅ Received response: %s\n", string(msg.Data))
		}
		
		requestID++
		
		// 다음 요청까지 1초 대기
		fmt.Printf("⏱️  Waiting 1 second before next request...\n")
		time.Sleep(1 * time.Second)
	}
}