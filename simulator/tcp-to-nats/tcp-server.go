package main

import (
	"encoding/binary"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"time"
)

// Message types (4.1.1.d)
const (
	MsgTypeHelloRequest         = 0x01
	MsgTypeHelloResponse        = 0x02
	MsgTypePingRequest          = 0x03
	MsgTypePingResponse         = 0x04
	MsgTypeSubsChangeRequest    = 0x05 // 업무 메시지
	MsgTypeSubsChangeResponse   = 0x06
)

// Command-line flags
var (
	sendRequests    = flag.Bool("send-requests", false, "Automatically send REQUEST messages")
	requestInterval = flag.Duration("request-interval", 200*time.Millisecond, "Interval between REQUEST messages")
	requestCount    = flag.Int("request-count", 0, "Number of requests to send (0 = unlimited)")
	listenPort      = flag.String("port", "8000", "TCP server listen port")
)

// 하위 호환성
const (
	FrameTypeHello    = MsgTypeHelloRequest
	FrameTypeAck      = MsgTypeHelloResponse
	FrameTypeRequest  = MsgTypeSubsChangeRequest
	FrameTypeResponse = MsgTypeSubsChangeResponse
	FrameTypePing     = MsgTypePingRequest
	FrameTypePong     = MsgTypePingResponse
)

// Frame structure (4.1)
// Header: 8 bytes
//   - Byte 1: Extension Bit(1) + Protocol Version(2) + Reserved(5) = 0x00
//   - Byte 2: Message Type
//   - Byte 3-4: Body Length (Big Endian, 2 bytes)
//   - Byte 5-8: Transaction Identifier (Big Endian, 4 bytes)
// Body: JSON (variable length)
type Frame struct {
	Type    uint8  `json:"type"`    // Message Type (Byte 2)
	Length  uint16 `json:"length"`  // Body Length (Byte 3-4)
	TID     uint32 `json:"tid"`     // Transaction Identifier (Byte 5-8)
	Payload []byte `json:"payload"` // Body (JSON)
}

// HandshakeRequest represents the HELLO handshake request message
type HandshakeRequest struct {
	SysID      string `json:"sys-id"`      // 접속하는 Peer Name
	BranchName string `json:"branch-name"` // 국사명 (SS/DS/BR)
}

// HandshakeResponse represents the ACK handshake response message
type HandshakeResponse struct {
	SysID        string `json:"sys-id"`        // 응답하는 Peer Name
	Code         int    `json:"code"`          // 결과 코드 (0=성공)
	PingInterval int    `json:"ping-interval"` // Ping 메시지 전송 주기 (초)
	Cause        string `json:"cause"`         // 실패 시 상세 사유 (optional)
}

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
	flag.Parse()

	fmt.Println("=== TCP Server (TCP→NATS Simulator) ===")
	fmt.Println("Waiting for tcp-bridge to connect (as client)")
	fmt.Println("Will send REQUEST frames and receive RESPONSE frames")
	fmt.Printf("📋 Configuration:\n")
	fmt.Printf("   - Port: %s\n", *listenPort)
	fmt.Printf("   - Send Requests: %v\n", *sendRequests)
	if *sendRequests {
		fmt.Printf("   - Request Interval: %v\n", *requestInterval)
		if *requestCount > 0 {
			fmt.Printf("   - Request Count: %d\n", *requestCount)
		} else {
			fmt.Printf("   - Request Count: unlimited\n")
		}
	}

	// Listen on configured port
	listener, err := net.Listen("tcp", ":"+*listenPort)
	if err != nil {
		log.Fatalf("Failed to start TCP server: %v", err)
	}
	defer listener.Close()

	fmt.Printf("🎧 TCP Server listening on :%s\n", *listenPort)
	fmt.Println("   Waiting for tcp-bridge connection...")

	for {
		// Accept incoming connection from tcp-bridge
		conn, err := listener.Accept()
		if err != nil {
			fmt.Printf("❌ Failed to accept connection: %v\n", err)
			continue
		}

		fmt.Printf("✅ tcp-bridge connected from %s\n", conn.RemoteAddr())

		// Handle connection in goroutine
		go handleConnection(conn)
	}
}

func handleConnection(conn net.Conn) {
	defer conn.Close()

	startTime := time.Now()
	fmt.Printf("[%s] 🔗 Connection started\n", time.Now().Format("15:04:05.000"))

	// Set TCP keepalive to maintain connection
	if tcpConn, ok := conn.(*net.TCPConn); ok {
		tcpConn.SetKeepAlive(true)
		tcpConn.SetKeepAlivePeriod(30 * time.Second)
	}

	// Perform handshake
	if !performHandshake(conn) {
		fmt.Printf("[%s] ❌ Handshake failed (duration: %v)\n", time.Now().Format("15:04:05.000"), time.Since(startTime))
		return
	}

	fmt.Printf("[%s] ✅ Handshake completed, connection ready (duration: %v)\n", time.Now().Format("15:04:05.000"), time.Since(startTime))
	fmt.Printf("📡 Connection info: LocalAddr=%s, RemoteAddr=%s\n", conn.LocalAddr(), conn.RemoteAddr())

	// Start response reader
	responseChan := make(chan *Frame, 10)
	go responseReader(conn, responseChan)

	// If send-requests flag is disabled, just wait for responses
	if !*sendRequests {
		fmt.Printf("[%s] 📭 Not sending requests (use -send-requests flag to enable)\n", time.Now().Format("15:04:05.000"))
		for response := range responseChan {
			if response == nil {
				duration := time.Since(startTime)
				fmt.Printf("[%s] 🔌 Connection closed (duration: %v)\n", time.Now().Format("15:04:05.000"), duration)
				return
			}
			var resp ResponsePayload
			if err := json.Unmarshal(response.Payload, &resp); err != nil {
				fmt.Printf("❌ Failed to parse response: %v\n", err)
				continue
			}
			fmt.Printf("[%s] ✅ Received RESPONSE TID=%d: %+v\n", time.Now().Format("15:04:05.000"), response.TID, resp)
		}
		return
	}

	// Send REQUEST frames periodically
	ticker := time.NewTicker(*requestInterval)
	defer ticker.Stop()

	requestID := 1
	tid := uint32(1000)
	sentCount := 0
	
	for {
		select {
		case <-ticker.C:
			// Check if we've reached the request count limit
			if *requestCount > 0 && sentCount >= *requestCount {
				fmt.Printf("✅ Sent %d requests (limit reached)\n", sentCount)
				ticker.Stop()
				// Continue listening for responses
				continue
			}

			// Create request payload with order message type
			request := RequestPayload{
				MessageType: "order", // Routes to internal_req.order
				RequestID:   requestID,
				Action:      "get_order_status",
				OrderID:     54321,
				Timestamp:   time.Now().Unix(),
			}

			// Convert to JSON
			requestData, err := json.Marshal(request)
			if err != nil {
				fmt.Printf("❌ Failed to marshal request: %v\n", err)
				continue
			}

			// Create REQUEST frame
			frame := &Frame{
				Type:    FrameTypeRequest,
				Length:  uint16(len(requestData)),
				TID:     tid,
				Payload: requestData,
			}

			fmt.Printf("\n🚀 ========== SENDING REQUEST ==========\n")
			fmt.Printf("   Request #%d (TID=%d)\n", requestID, tid)
			
			// Create header for logging
			header := make([]byte, 8)
			header[0] = 0x00
			header[1] = frame.Type
			binary.BigEndian.PutUint16(header[2:4], frame.Length)
			binary.BigEndian.PutUint32(header[4:8], frame.TID)
			
			fmt.Printf("   Header (8 bytes): %02X %02X %02X %02X %02X %02X %02X %02X\n",
				header[0], header[1], header[2], header[3],
				header[4], header[5], header[6], header[7])
			fmt.Printf("   Byte 1: 0x%02X\n", header[0])
			fmt.Printf("   Byte 2: Message Type=0x%02X (%d)\n", frame.Type, frame.Type)
			fmt.Printf("   Byte 3-4: Body Length=%d (0x%04X)\n", frame.Length, frame.Length)
			fmt.Printf("   Byte 5-8: TID=%d (0x%08X)\n", frame.TID, frame.TID)
			fmt.Printf("   Body (%d bytes): %s\n", len(requestData), string(requestData))
			fmt.Printf("========================================\n")

			// Send frame
			if err := sendFrame(conn, frame); err != nil {
				fmt.Printf("❌ Failed to send request: %v\n", err)
				return
			}

			requestID++
			tid++
			sentCount++

		case response := <-responseChan:
			// Response received from responseReader goroutine
			if response == nil {
				fmt.Println("🔌 Connection closed")
				return
			}

			var resp ResponsePayload
			if err := json.Unmarshal(response.Payload, &resp); err != nil {
				fmt.Printf("❌ Failed to parse response: %v\n", err)
				continue
			}

			fmt.Printf("✅ Received RESPONSE TID=%d: %+v\n", response.TID, resp)
		}
	}
	
}

// performHandshake handles the HELLO/ACK handshake with JSON protocol
func performHandshake(conn net.Conn) bool {
	fmt.Println("🤝 Waiting for HELLO handshake...")

	// Read HELLO frame header (8 bytes, 4.1.1)
	header := make([]byte, 8)
	if _, err := io.ReadFull(conn, header); err != nil {
		fmt.Printf("❌ Failed to read HELLO header: %v\n", err)
		return false
	}

	// Parse header
	// Byte 1: Extension Bit + Protocol Version + Reserved
	extVersion := (header[0] >> 7) & 0x01
	protocolVer := (header[0] >> 5) & 0x03
	if protocolVer != 0 || extVersion != 0 {
		fmt.Printf("❌ Unsupported protocol version=%d, ext=%d\n", protocolVer, extVersion)
		return false
	}

	// Byte 2: Message Type
	frameType := header[1]
	// Byte 3-4: Body Length
	length := binary.BigEndian.Uint16(header[2:4])
	// Byte 5-8: Transaction Identifier
	tid := binary.BigEndian.Uint32(header[4:8])

	if frameType != FrameTypeHello {
		fmt.Printf("❌ Expected HELLO, got frame type: 0x%02X\n", frameType)
		return false
	}

	// Read HELLO payload
	var helloReq HandshakeRequest
	if length > 0 {
		payload := make([]byte, length)
		if _, err := io.ReadFull(conn, payload); err != nil {
			fmt.Printf("❌ Failed to read HELLO payload: %v\n", err)
			return false
		}
		
		if err := json.Unmarshal(payload, &helloReq); err != nil {
			fmt.Printf("❌ Failed to unmarshal HELLO: %v\n", err)
			return false
		}
	}

	fmt.Printf("✅ Received HELLO (TID=%d, sys-id=%s, branch-name=%s)\n", 
		tid, helloReq.SysID, helloReq.BranchName)

	// Prepare ACK response
	ackResp := HandshakeResponse{
		SysID:        "tcp-server-01",
		Code:         0, // Success
		PingInterval: 10, // 30 seconds ping interval
		Cause:        "",
	}
	
	ackPayload, err := json.Marshal(ackResp)
	if err != nil {
		fmt.Printf("❌ Failed to marshal ACK: %v\n", err)
		return false
	}

	// Send ACK response
	ackFrame := &Frame{
		Type:    FrameTypeAck,
		Length:  uint16(len(ackPayload)),
		TID:     tid,
		Payload: ackPayload,
	}

	if err := sendFrame(conn, ackFrame); err != nil {
		fmt.Printf("❌ Failed to send ACK: %v\n", err)
		return false
	}

	fmt.Printf("✅ Sent ACK (TID=%d, ping-interval=%d)\n", tid, ackResp.PingInterval)
	return true
}

// responseReader continuously reads frames from the connection
func responseReader(conn net.Conn, responseChan chan<- *Frame) {
	defer close(responseChan)

	fmt.Printf("[%s] 📖 Response reader started, waiting for frames...\n", time.Now().Format("15:04:05.000"))
	
	for {
		// Read frame header (8 bytes, 4.1.1)
		header := make([]byte, 8)
		if _, err := io.ReadFull(conn, header); err != nil {
			if err == io.EOF {
				fmt.Printf("[%s] 📡 Connection closed by remote (EOF)\n", time.Now().Format("15:04:05.000"))
			} else {
				fmt.Printf("[%s] ❌ Failed to read frame header: %v\n", time.Now().Format("15:04:05.000"), err)
			}
			responseChan <- nil
			return
		}

		// Parse header (4.1.1)
		// Byte 1: Extension Bit + Protocol Version + Reserved
		extVersion := (header[0] >> 7) & 0x01
		protocolVer := (header[0] >> 5) & 0x03
		reserved := header[0] & 0x1F
		// Byte 2: Message Type
		frameType := header[1]
		// Byte 3-4: Body Length
		length := binary.BigEndian.Uint16(header[2:4])
		// Byte 5-8: Transaction Identifier
		tid := binary.BigEndian.Uint32(header[4:8])

		// Print header details
		fmt.Printf("\n📨 ========== RECEIVED RESPONSE ==========\n")
		fmt.Printf("   Header (8 bytes): %02X %02X %02X %02X %02X %02X %02X %02X\n",
			header[0], header[1], header[2], header[3],
			header[4], header[5], header[6], header[7])
		fmt.Printf("   Byte 1: Ext=%d, Ver=%d, Reserved=0x%02X\n", extVersion, protocolVer, reserved)
		fmt.Printf("   Byte 2: Message Type=0x%02X (%d)\n", frameType, frameType)
		fmt.Printf("   Byte 3-4: Body Length=%d (0x%04X)\n", length, length)
		fmt.Printf("   Byte 5-8: TID=%d (0x%08X)\n", tid, tid)

		// Read payload
		var payload []byte
		if length > 0 {
			payload = make([]byte, length)
			if _, err := io.ReadFull(conn, payload); err != nil {
				fmt.Printf("❌ Failed to read payload: %v\n", err)
				responseChan <- nil
				return
			}
			fmt.Printf("   Body (%d bytes): %s\n", length, string(payload))
		}
		fmt.Printf("========================================\n")

		// Handle frame by type
		if frameType == FrameTypeResponse {
			frame := &Frame{
				Type:    frameType,
				Length:  length,
				TID:     tid,
				Payload: payload,
			}
			responseChan <- frame
		} else if frameType == FrameTypePing {
			// Received PING, send PONG
			fmt.Printf("[%s] 📡 Received PING (TID=%d), sending PONG\n", time.Now().Format("15:04:05.000"), tid)
			pongFrame := &Frame{
				Type:    FrameTypePong,
				Length:  0,
				TID:     tid, // 받은 PING의 TID를 그대로 응답
				Payload: nil,
			}
			if err := sendFrame(conn, pongFrame); err != nil {
				fmt.Printf("[%s] ❌ Failed to send PONG: %v\n", time.Now().Format("15:04:05.000"), err)
			}
		} else if frameType == FrameTypePong {
			fmt.Printf("[%s] 📡 Received PONG (TID=%d)\n", time.Now().Format("15:04:05.000"), tid)
		} else {
			fmt.Printf("[%s] ⚠️  Unexpected frame type during operation: 0x%02X\n", time.Now().Format("15:04:05.000"), frameType)
		}
	}
}

// sendFrame sends a frame to the connection (4.1)
func sendFrame(conn net.Conn, frame *Frame) error {
	// Create header (8 bytes)
	header := make([]byte, 8)
	// Byte 1: Extension Bit(0) + Protocol Version(0) + Reserved(0)
	header[0] = 0x00
	// Byte 2: Message Type
	header[1] = frame.Type
	// Byte 3-4: Body Length (Big Endian)
	binary.BigEndian.PutUint16(header[2:4], frame.Length)
	// Byte 5-8: Transaction Identifier (Big Endian)
	binary.BigEndian.PutUint32(header[4:8], frame.TID)

	// Send header + payload
	data := append(header, frame.Payload...)
	_, err := conn.Write(data)
	return err
}
