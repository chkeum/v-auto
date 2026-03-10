package main

import (
	"bufio"
	"encoding/binary"
	"encoding/json"
	"flag"
	"fmt"
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
	MessageType string      `json:"message_type"`
	RequestID   int         `json:"request_id"`
	Action      string      `json:"action"`
	UserID      int         `json:"user_id"`
	Timestamp   int64       `json:"timestamp"`
}

// Response payload structure
type ResponsePayload struct {
	RequestID   int         `json:"request_id"`
	Status      string      `json:"status"`
	Data        interface{} `json:"data"`
	Timestamp   int64       `json:"timestamp"`
	ProcessedBy string      `json:"processed_by"`
}

var (
	listenPort = flag.String("port", "8000", "TCP server listen port")
)

func main() {
	flag.Parse()
	
	fmt.Println("=== TCP Server (NATS→TCP Simulator) ===")
	fmt.Println("This server receives requests from tcp-bridge")
	fmt.Println("And sends responses back")
	fmt.Printf("📋 Configuration: Port=%s\n", *listenPort)
	
	// Listen on configured port
	listener, err := net.Listen("tcp", ":"+*listenPort)
	if err != nil {
		log.Fatalf("Failed to listen on port %s: %v", *listenPort, err)
	}
	defer listener.Close()
	
	fmt.Printf("✅ TCP Server listening on :%s\n", *listenPort)
	fmt.Println("🔗 Waiting for tcp-bridge connection...")
	
	for {
		conn, err := listener.Accept()
		if err != nil {
			log.Printf("❌ Failed to accept connection: %v", err)
			continue
		}
		
		fmt.Printf("🔗 New connection from %s\n", conn.RemoteAddr())
		go handleConnection(conn)
	}
}

func handleConnection(conn net.Conn) {
	defer conn.Close()
	reader := bufio.NewReader(conn)
	
	for {
		// Read frame header (8 bytes, 4.1.1)
		header := make([]byte, 8)
		_, err := reader.Read(header)
		if err != nil {
			fmt.Printf("🔌 Connection closed: %v\n", err)
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
		fmt.Printf("\n📨 ========== RECEIVED FRAME ==========\n")
		fmt.Printf("   Header (8 bytes): %02X %02X %02X %02X %02X %02X %02X %02X\n",
			header[0], header[1], header[2], header[3],
			header[4], header[5], header[6], header[7])
		fmt.Printf("   Byte 1: Ext=%d, Ver=%d, Reserved=0x%02X\n", extVersion, protocolVer, reserved)
		fmt.Printf("   Byte 2: Message Type=0x%02X (%d)\n", frameType, frameType)
		fmt.Printf("   Byte 3-4: Body Length=%d (0x%04X)\n", length, length)
		fmt.Printf("   Byte 5-8: TID=%d (0x%08X)\n", tid, tid)
		
		// Read payload
		payload := make([]byte, length)
		_, err = reader.Read(payload)
		if err != nil {
			fmt.Printf("❌ Failed to read payload: %v\n", err)
			return
		}
		
		fmt.Printf("   Body (%d bytes): %s\n", length, string(payload))
		fmt.Printf("========================================\n")
		
		frame := &Frame{
			Type:    frameType,
			Length:  length,
			TID:     tid,
			Payload: payload,
		}
		
		if frameType == FrameTypeHello {
			handleHandshake(conn, frame)
		} else if frameType == FrameTypeRequest {
			handleRequest(conn, frame)
		} else if frameType == FrameTypePing {
			handlePing(conn, frame)
		} else if frameType == FrameTypePong {
			fmt.Printf("📡 Received PONG (TID=%d)\n", frame.TID)
		} else {
			fmt.Printf("⚠️  Unknown frame type: %d\n", frameType)
		}
	}
}

func handleRequest(conn net.Conn, frame *Frame) {
	// Parse request payload
	var req RequestPayload
	if err := json.Unmarshal(frame.Payload, &req); err != nil {
		fmt.Printf("❌ Failed to parse request: %v\n", err)
		return
	}
	
	fmt.Printf("   Request: %+v\n", req)
	
	// Simulate processing time - sleep 10초
	fmt.Printf("   💤 Sleeping 3 seconds before response...\n")
	time.Sleep(3 * time.Second)
	
	// Create response payload
	response := ResponsePayload{
		RequestID: req.RequestID,
		Status:    "success",
		Data: map[string]interface{}{
			"user_id":     req.UserID,
			"profile":     map[string]interface{}{
				"name":  "John Doe",
				"email": "john@example.com",
				"role":  "admin",
			},
			"last_login": time.Now().Unix(),
		},
		Timestamp:   time.Now().Unix(),
		ProcessedBy: "tcp-server",
	}
	
	// Convert to JSON
	responseData, err := json.Marshal(response)
	if err != nil {
		fmt.Printf("❌ Failed to marshal response: %v", err)
		return
	}
	
	// Create response frame
	responseFrame := &Frame{
		Type:    FrameTypeResponse,
		Length:  uint16(len(responseData)),
		TID:     frame.TID,
		Payload: responseData,
	}
	
	// Send response
	if err := sendFrame(conn, responseFrame); err != nil {
		fmt.Printf("❌ Failed to send response: %v", err)
		return
	}
	
	fmt.Printf("✅ Sent response TID=%d: %s\n", responseFrame.TID, string(responseData))
}

func handleHandshake(conn net.Conn, frame *Frame) {
	// Parse HELLO request
	var helloReq HandshakeRequest
	if len(frame.Payload) > 0 {
		if err := json.Unmarshal(frame.Payload, &helloReq); err != nil {
			fmt.Printf("❌ Failed to parse HELLO: %v\n", err)
			return
		}
	}
	
	fmt.Printf("🤝 Received HELLO handshake (sys-id=%s, branch-name=%s)\n", helloReq.SysID, helloReq.BranchName)
	
	// Prepare ACK response
	ackResp := HandshakeResponse{
		SysID:        "tcp-server-01",
		Code:         0, // Success
		PingInterval: 30, // 30 seconds ping interval
		Cause:        "",
	}
	
	ackPayload, err := json.Marshal(ackResp)
	if err != nil {
		fmt.Printf("❌ Failed to marshal ACK: %v\n", err)
		return
	}
	
	// Create ACK frame
	ackFrame := &Frame{
		Type:    FrameTypeAck,
		Length:  uint16(len(ackPayload)),
		TID:     frame.TID,
		Payload: ackPayload,
	}
	
	// Send ACK response
	if err := sendFrame(conn, ackFrame); err != nil {
		fmt.Printf("❌ Failed to send ACK: %v\n", err)
		return
	}
	
	fmt.Printf("✅ Sent ACK handshake (TID=%d, ping-interval=%d)\n", ackFrame.TID, ackResp.PingInterval)
}

func handlePing(conn net.Conn, frame *Frame) {
	fmt.Printf("📡 Received PING (TID=%d), sending PONG\n", frame.TID)
	
	// Create PONG frame (no payload)
	pongFrame := &Frame{
		Type:    FrameTypePong,
		Length:  0,
		TID:     frame.TID, // 받은 PING의 TID를 그대로 응답
		Payload: nil,
	}
	
	// Send PONG response
	if err := sendFrame(conn, pongFrame); err != nil {
		fmt.Printf("❌ Failed to send PONG: %v\n", err)
		return
	}
}

func sendFrame(conn net.Conn, frame *Frame) error {
	// Create header (8 bytes, 4.1)
	header := make([]byte, 8)
	// Byte 1: Extension Bit(0) + Protocol Version(0) + Reserved(0)
	header[0] = 0x00
	// Byte 2: Message Type
	header[1] = frame.Type
	// Byte 3-4: Body Length (Big Endian)
	binary.BigEndian.PutUint16(header[2:4], frame.Length)
	// Byte 5-8: Transaction Identifier (Big Endian)
	binary.BigEndian.PutUint32(header[4:8], frame.TID)
	
	// Log sending details
	if frame.Type == FrameTypeResponse || frame.Type == FrameTypeAck {
		fmt.Printf("\n📤 ========== SENDING RESPONSE ==========\n")
		fmt.Printf("   Header (8 bytes): %02X %02X %02X %02X %02X %02X %02X %02X\n",
			header[0], header[1], header[2], header[3],
			header[4], header[5], header[6], header[7])
		fmt.Printf("   Byte 1: 0x%02X\n", header[0])
		fmt.Printf("   Byte 2: Message Type=0x%02X (%d)\n", frame.Type, frame.Type)
		fmt.Printf("   Byte 3-4: Body Length=%d (0x%04X)\n", frame.Length, frame.Length)
		fmt.Printf("   Byte 5-8: TID=%d (0x%08X)\n", frame.TID, frame.TID)
		if len(frame.Payload) > 0 {
			fmt.Printf("   Body (%d bytes): %s\n", len(frame.Payload), string(frame.Payload))
		}
		fmt.Printf("========================================\n")
	}
	
	// Send header + payload
	_, err := conn.Write(append(header, frame.Payload...))
	return err
}