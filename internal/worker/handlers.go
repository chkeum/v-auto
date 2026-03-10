package worker

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sync/atomic"
	"time"

	"tcp-bridge/internal/config"
	"tcp-bridge/internal/connection"
	"tcp-bridge/internal/inflight"
	tcpnats "tcp-bridge/internal/nats"
	"tcp-bridge/internal/tcp"

	"github.com/nats-io/nats.go"
)

// globalTIDCounter는 thread-safe한 TID 생성을 위한 전역 atomic 카운터입니다.
// TID (Transaction ID)는 요청과 응답을 매칭하기 위한 고유 식별자입니다.
//
// 주의사항:
//   - atomic 연산을 사용하므로 여러 고루틴에서 동시에 안전하게 사용 가능
//   - uint32 범위 (0 ~ 4,294,967,295)를 초과하면 1로 재설정됨
//   - 매일 자정에 카운터가 1로 리셋됨
//   - TID는 0을 반환하지 않음 (1부터 시작)
var (
	globalTIDCounter uint32 // TID counter (starts from 0, first call returns 1)
	lastResetDate    int32  // Last reset date in YYYYMMDD format
)

// NATSInboundHandler는 NATS 메시지를 처리하고 TCP로 전달하는 통합 메시지 핸들러입니다.
// NATS Queue Group을 사용하여 로드 밸런싱을 수행하며, RPC 패턴을 지원합니다.
//
// 메시지 플로우:
//   1. NATS→TCP (RPC): NATS 요청 수신 → TCP 전송 → TCP 응답 대기 → NATS 응답
//   2. NATS→TCP (Fire-and-forget): NATS 요청 수신 → TCP 전송 → 즉시 ACK
//
// 동시성:
//   - NATS Queue Group의 각 메시지는 별도 고루틴에서 처리됨
//   - HandleExternalRequest는 여러 고루틴에서 동시에 호출될 수 있음
//   - 내부적으로 tcpSender와 inflightMgr가 동시성을 처리함
type NATSInboundHandler struct {
	logger      *slog.Logger
	config      *config.MessageHandlerPoolConfig
	natsConfig  *config.NATSConfig
	
	// Dependencies (모두 thread-safe함)
	natsClient  *tcpnats.Client
	tcpSender   *tcp.Sender           // Mutex로 보호됨
	inflightMgr *inflight.InflightManager  // Mutex로 보호됨
	connMgr     *connection.ConnectionManager // Priority 기반 재시도용

	// Lifecycle
	ctx    context.Context
	cancel context.CancelFunc
}

// NewNATSInboundHandler creates a new NATS inbound handler
func NewNATSInboundHandler(
	logger *slog.Logger,
	config *config.MessageHandlerPoolConfig,
	natsConfig *config.NATSConfig,
	natsClient *tcpnats.Client,
	tcpSender *tcp.Sender,
	inflightMgr *inflight.InflightManager,
	connMgr *connection.ConnectionManager,
) *NATSInboundHandler {
	ctx, cancel := context.WithCancel(context.Background())
	
	return &NATSInboundHandler{
		logger:      logger,
		config:      config,
		natsConfig:  natsConfig,
		natsClient:  natsClient,
		tcpSender:   tcpSender,
		inflightMgr: inflightMgr,
		connMgr:     connMgr,
		ctx:         ctx,
		cancel:      cancel,
	}
}

// Start starts the NATS inbound handler by subscribing to NATS with Queue Group
func (nh *NATSInboundHandler) Start(ctx context.Context) error {
	nh.logger.Info("starting NATS inbound handler with NATS queue groups")
	
	// Subscribe to external_req with queue group for load balancing
	subscriber := nh.natsClient.GetSubscriber()
	err := subscriber.SubscribeWithQueue("tcp-bridge-workers", nh.HandleExternalRequest)
	if err != nil {
		return fmt.Errorf("failed to subscribe to external requests: %w", err)
	}
	
	nh.logger.Info("NATS inbound handler started with queue group subscription")
	return nil
}

// Stop stops the NATS inbound handler
func (nh *NATSInboundHandler) Stop() {
	nh.logger.Info("stopping NATS inbound handler")
	
	nh.cancel()
	
	// Unsubscribe from NATS
	subscriber := nh.natsClient.GetSubscriber()
	if err := subscriber.Unsubscribe(); err != nil {
		nh.logger.Error("error unsubscribing from NATS", "error", err)
	}
	
	nh.logger.Info("NATS inbound handler stopped")
}

// HandleExternalRequest는 NATS→TCP 메시지를 처리합니다.
// NATS Queue Group의 각 worker가 병렬로 호출하므로 thread-safe해야 합니다.
//
// NATS → TCP 방향:
//   - 요청 타입: 0x01 (Hello), 0x03 (Ping), 0x05 (Subs-Change), 0x09 (CellInfo-Noti)
//   - TCP 응답은 payload만 NATS로 전송 (헤더 제거)
//
// 처리 플로우:
//   1. TID 생성 (요청/응답 매칭용)
//   2. Message Type 결정 (메시지에서 추출 또는 기본값)
//   3. TCP 프레임 생성
//   4. Priority 순회하며 재시도: 각 connection에 retry_attempts번씩 시도
//   5. RPC 요청: 응답 대기 (response_timeout 설정)
//   6. fire-and-forget: 즉시 ACK
//
// 재시도 전략 (VIP 절체 대응):
//   - Priority 0에서 retry_attempts번 시도 (즉시 재시도)
//   - 실패 시 Priority 1로 이동하여 동일하게 시도
//   - 모든 connection 실패 시 timeout 응답
//
// 동시성:
//   - 여러 고루틴에서 동시에 호출 가능
//   - tcpSender와 inflightMgr가 내부적으로 lock 처리
func (nh *NATSInboundHandler) HandleExternalRequest(msg *nats.Msg) {
	logger := nh.logger.With("subject", msg.Subject, "reply", msg.Reply)
	logger.Debug("processing external request")
	
	// TID 생성 (thread-safe atomic increment)
	tid := generateTID()
	isRPC := msg.Reply != ""
	
	// Determine Message Type (4.1.1.d)
	// NATS→TCP 요청: 0x01, 0x03, 0x05, 0x09
	msgType := nh.determineMessageType(msg.Data, msg.Subject)
	
	// Validate: NATS→TCP request should be 0x01, 0x03, 0x05, or 0x09
	frame := &config.Frame{Type: msgType}
	if !frame.IsNATSToTCPRequest() && msgType != config.MsgTypeSubsChangeRequest {
		logger.Warn("unexpected message type for NATS→TCP flow, using default 0x05", 
			"original_type", fmt.Sprintf("0x%02x", msgType))
		msgType = config.MsgTypeSubsChangeRequest // Default to Subs-Change-Request
	}
	
	// TCP 프레임 생성
	frame = &config.Frame{
		Type:    msgType,
		TID:     tid,
		Payload: msg.Data,
	}
	
	// RPC 요청인 경우 inflight 등록
	var inflightEntry *inflight.InflightEntryA
	if isRPC {
		// 전체 재시도 시간을 고려한 deadline 계산
		// = retry_attempts × response_timeout × endpoints 수
		retryAttempts := nh.config.RetryAttempts
		if retryAttempts == 0 {
			retryAttempts = 3
		}
		responseTimeout := nh.config.ResponseTimeout
		if responseTimeout == 0 {
			responseTimeout = 5 * time.Second
		}
		
		// 전체 재시도 시간 + 여유 시간(10초)
		connections := nh.connMgr.GetConnections()
		priorityCount := len(connections)
		totalTimeout := time.Duration(retryAttempts*priorityCount) * responseTimeout + 10*time.Second
		deadline := time.Now().Add(totalTimeout).Unix()
		
		inflightEntry = nh.inflightMgr.GetInflightA().Register(tid, msg.Reply, msg.Data, deadline, "P")
		logger.Debug("registered inflight-A entry", "tid", tid, "msg_type", fmt.Sprintf("0x%02x", msgType), "deadline_seconds", totalTimeout.Seconds())
	}
	
	// Priority 기반 재시도 전략 (전송 + 응답 대기 통합)
	success := nh.sendAndWaitWithRetry(frame, inflightEntry, isRPC, logger)
	
	if !success {
		logger.Error("all connection attempts failed", "tid", tid)
		if isRPC {
			nh.inflightMgr.GetInflightA().Remove(tid)
			nh.replyError(msg, "all TCP connections failed or timeout")
		}
		msg.Ack() // 재시도 완료했으므로 ACK
		return
	}
	
	logger.Debug("request processed successfully", "tid", tid)
	msg.Ack()
}

// sendAndWaitWithRetry는 priority 순서대로 connection을 시도하며 프레임을 전송하고 응답을 대기합니다.
// 각 connection에 대해 retry_attempts번씩 시도합니다.
// VIP 절체 상황을 대응하기 위한 재시도 로직입니다.
//
// 재시도 전략:
//   1. 전송 실패 시: 즉시 재시도
//   2. 전송 성공 but 응답 timeout: 즉시 재시도 (VIP 절체 대응)
//   3. 모든 시도 실패 시: 다음 priority로 이동
//
// 반환값: 성공 시 true (응답 수신 또는 fire-and-forget 전송 성공), 모든 시도 실패 시 false
func (nh *NATSInboundHandler) sendAndWaitWithRetry(frame *config.Frame, inflightEntry *inflight.InflightEntryA, isRPC bool, logger *slog.Logger) bool {
	connections := nh.connMgr.GetConnections()
	retryAttempts := nh.config.RetryAttempts
	if retryAttempts == 0 {
		retryAttempts = 3 // 기본값
	}
	responseTimeout := nh.config.ResponseTimeout
	if responseTimeout == 0 {
		responseTimeout = 5 * time.Second // 기본값
	}
	
	// Priority 순서대로 시도
	for priority := 0; priority < len(connections); priority++ {
		conn := connections[priority]
		if conn == nil {
			continue
		}
		
		// Connection READY 상태 확인 (priority 단위로 체크)
		if conn.GetState() != config.ConnStateReady {
			logger.Debug("connection not ready, skipping to next priority",
				"tid", frame.TID,
				"priority", priority,
				"state", conn.GetState())
			continue // 이 priority 포기, 다음 priority로
		}
		
		// 각 connection에 대해 retry_attempts번 시도
		for attempt := 1; attempt <= retryAttempts; attempt++ {
			// 프레임 직렬화
			data, err := frame.Serialize()
			if err != nil {
				logger.Error("failed to serialize frame", "tid", frame.TID, "error", err)
				return false // 직렬화 실패는 재시도 불가
			}
			
			// 특정 connection으로 전송
			bytesWritten, err := conn.Write(data)
			if err != nil {
				logger.Warn("TCP send failed",
					"tid", frame.TID,
					"priority", priority,
					"attempt", attempt,
					"error", err)
				
				// 전송 실패: 즉시 재시도
				continue
			}
			
			// 전송 성공 확인
			if bytesWritten != len(data) {
				logger.Error("incomplete write",
					"tid", frame.TID,
					"priority", priority,
					"wrote", bytesWritten,
					"expected", len(data))
				
				continue
			}
			
			logger.Info("TCP frame sent successfully",
				"tid", frame.TID,
				"priority", priority,
				"attempt", attempt,
				"bytes", bytesWritten)
			
			// Fire-and-forget: 전송 성공하면 즉시 반환
			if !isRPC {
				return true
			}
			
			// RPC: 응답 대기
			select {
			case responseFrame := <-inflightEntry.ResponseChan:
				// TCP 응답 수신 - NATS reply 전송
				// NATS→TCP 방향: TCP 응답의 payload만 NATS로 전송 (헤더 제거)
				logger.Info("received TCP response",
					"tid", frame.TID,
					"priority", priority,
					"attempt", attempt,
					"response_type", fmt.Sprintf("0x%02x", responseFrame.Type),
					"response_size", len(responseFrame.Payload))
				
				// 응답 타입 검증
				expectedRespType := nh.natsConfig.MessageTypeRouting.GetResponseType(frame.Type)
				if expectedRespType != 0 && responseFrame.Type != expectedRespType {
					logger.Warn("unexpected response type",
						"tid", frame.TID,
						"expected", fmt.Sprintf("0x%02x", expectedRespType),
						"actual", fmt.Sprintf("0x%02x", responseFrame.Type))
					// Continue anyway - just warning
				}
				
				replyPublisher := nh.natsClient.GetReplyPublisher()
				// TCP 응답의 payload만 NATS로 전송 (헤더는 제거)
				if err := replyPublisher.PublishReply(inflightEntry.ReplySubject, responseFrame.Payload); err != nil {
					logger.Error("failed to send NATS reply", "tid", frame.TID, "error", err)
					return false
				}
				
				logger.Debug("sent NATS reply (payload only)", "tid", frame.TID, "size", len(responseFrame.Payload))
				return true // 성공!
				
			case <-time.After(responseTimeout):
				// 응답 timeout: 즉시 재시도
				logger.Warn("response timeout, retrying",
					"tid", frame.TID,
					"priority", priority,
					"attempt", attempt,
					"response_timeout", responseTimeout)
				
				continue // 재시도
			}
		}
		
		// 이 priority의 모든 시도 실패, 다음 priority로
		logger.Warn("all attempts failed for priority, trying next",
			"tid", frame.TID,
			"failed_priority", priority,
			"attempts", retryAttempts)
	}
	
	// 모든 connection 시도 실패
	return false
}

// HandleTCPRequest processes incoming TCP requests and sends to NATS
// TCP → NATS 방향: TCP에서 요청을 받아 NATS로 전달하고, 응답을 TCP로 반환
//
// 처리 흐름 (예: 0x07 Subs-Info-Request):
//   1. TCP에서 0x07 요청 수신 (헤더 + payload)
//   2. Message Type으로 NATS subject 검색: 0x07 → "tcp.subs.info"
//   3. NATS로 payload만 전송 (헤더 제거)
//   4. NATS 응답 수신 (payload)
//   5. 응답 타입 자동 계산: 0x07 + 1 = 0x08
//   6. TCP로 응답 전송 (헤더[0x08] + payload)
//
// 참고: Response 타입(0x08, 0x0c)은 매핑 불필요, 코드에서 자동 계산
func (nh *NATSInboundHandler) HandleTCPRequest(frame *config.Frame) {
	// This will be called by TCP Reader when REQUEST frame is received
	
	logger := nh.logger.With("tid", frame.TID, "msg_type", fmt.Sprintf("0x%02x", frame.Type))
	logger.Debug("processing TCP request")
	
	// Validate: TCP→NATS request should be 0x07 or 0x0b
	if !frame.IsTCPToNATSRequest() {
		logger.Warn("received non-TCP→NATS request type, processing anyway", "type", frame.Type)
		// Continue processing for backward compatibility
	}
	
	// Determine NATS subject based on Message Type (4.1.1.d)
	subject := nh.natsConfig.MessageTypeRouting.GetSubjectForMessageType(frame.Type)
	if subject == "" {
		logger.Error("unknown message type, dropping", 
			"msg_type", fmt.Sprintf("0x%02x", frame.Type),
			"connection_id", frame.ConnectionID)
		return
	}
	logger.Debug("routing to NATS", "subject", subject)
	
	// Calculate deadline
	deadline := time.Now().Add(nh.config.Timeout).Unix()
	
	// Get response message type from configuration
	// TCP→NATS 방향: 설정에서 명시적으로 지정된 응답 타입 사용
	responseType := nh.natsConfig.MessageTypeRouting.GetResponseType(frame.Type)
	if responseType == 0 {
		// Fallback: 자동 계산 (설정 누락 대응)
		responseType = frame.GetResponseType()
		logger.Warn("response type not configured, using auto-calculated type",
			"request_type", fmt.Sprintf("0x%02x", frame.Type),
			"response_type", fmt.Sprintf("0x%02x", responseType))
	}
	
	logger.Debug("determined response type",
		"request_type", fmt.Sprintf("0x%02x", frame.Type),
		"response_type", fmt.Sprintf("0x%02x", responseType))
	
	// Register in inflight-B (TCP requests always tracked)
	tcpReplyInfo := &inflight.TCPReplyInfo{
		ConnectionID: frame.ConnectionID, // Use actual connection ID
		FrameType:    responseType,
	}
	nh.inflightMgr.GetInflightB().Register(frame.TID, tcpReplyInfo, frame.Payload, deadline)
	
	// Send request to NATS (payload만 전송, 4.1.2)
	// TCP→NATS 방향: NATS로는 payload만 전송 (헤더 제거)
	requester := nh.natsClient.GetRequester()
	response, err := requester.RequestWithTimeoutToSubject(subject, frame.Payload, nh.config.Timeout)
	if err != nil {
		logger.Error("NATS request failed", "subject", subject, "error", err)
		nh.inflightMgr.GetInflightB().Remove(frame.ConnectionID, frame.TID)
		nh.sendTCPErrorResponse(frame.TID, responseType, "internal error")
		return
	}
	
	logger.Debug("received NATS response", "subject", subject, "response_size", len(response))
	
	// Send TCP response to the originating connection
	// TCP→NATS 방향: NATS 응답을 TCP로 전송 시 헤더 포함 (메시지 타입 = 요청 타입 + 1)
	nh.sendTCPResponseToConnection(frame.ConnectionID, frame.TID, responseType, response)
	
	// Remove from inflight
	nh.inflightMgr.GetInflightB().Remove(frame.ConnectionID, frame.TID)
}

// determineNATSSubject determines the NATS subject based on routing rules (Deprecated)
func (nh *NATSInboundHandler) determineNATSSubject(payload []byte) string {
	if nh.natsConfig.RoutingRules.Field == "" {
		return nh.natsConfig.RoutingRules.DefaultSubject
	}
	
	// Parse JSON to extract routing field
	var data map[string]interface{}
	if err := json.Unmarshal(payload, &data); err != nil {
		nh.logger.Debug("failed to parse JSON for routing, using default subject", "error", err)
		return nh.natsConfig.RoutingRules.DefaultSubject
	}
	
	// Get field value
	fieldValue, ok := data[nh.natsConfig.RoutingRules.Field].(string)
	if !ok {
		nh.logger.Debug("routing field not found or not string, using default subject", 
			"field", nh.natsConfig.RoutingRules.Field)
		return nh.natsConfig.RoutingRules.DefaultSubject
	}
	
	// Check mapping
	if mappedSubject, exists := nh.natsConfig.RoutingRules.Mapping[fieldValue]; exists {
		nh.logger.Debug("mapped subject found", "field_value", fieldValue, "subject", mappedSubject)
		return mappedSubject
	}
	
	nh.logger.Debug("no mapping found, using default subject", "field_value", fieldValue)
	return nh.natsConfig.RoutingRules.DefaultSubject
}

// determineMessageType determines the TCP Message Type for NATS→TCP messages
// Checks payload for "msg_type" field (hex string), otherwise uses default (0x05)
//
// 처리 흐름:
//   1. Payload에서 "msg_type" 필드 추출 시도 (hex string or number)
//   2. 없으면 기본값 0x05 (Subs-Change-Request) 사용
//
// 참고: NATS→TCP 요청은 0x05, 0x09만 사용 (Hello/Ping은 제외)
func (nh *NATSInboundHandler) determineMessageType(payload []byte, subject string) uint8 {
	// Try to parse JSON and extract msg_type field
	var data map[string]interface{}
	if err := json.Unmarshal(payload, &data); err == nil {
		if msgTypeStr, ok := data["msg_type"].(string); ok {
			// Parse hex string (e.g., "05" or "0x05")
			var msgType uint8
			if len(msgTypeStr) >= 2 {
				if msgTypeStr[:2] == "0x" || msgTypeStr[:2] == "0X" {
					fmt.Sscanf(msgTypeStr[2:], "%02x", &msgType)
				} else {
					fmt.Sscanf(msgTypeStr, "%02x", &msgType)
				}
				if msgType > 0 {
					nh.logger.Debug("message type from payload", "msg_type", fmt.Sprintf("0x%02x", msgType))
					return msgType
				}
			}
		}
		
		// Try numeric msg_type field
		if msgTypeNum, ok := data["msg_type"].(float64); ok {
			msgType := uint8(msgTypeNum)
			nh.logger.Debug("message type from payload (numeric)", "msg_type", fmt.Sprintf("0x%02x", msgType))
			return msgType
		}
	}
	
	// Default: use Subs-Change-Request (0x05) for NATS→TCP
	defaultMsgType := config.MsgTypeSubsChangeRequest
	nh.logger.Debug("using default message type", "msg_type", fmt.Sprintf("0x%02x", defaultMsgType), "subject", subject)
	return defaultMsgType
}

// sendTCPResponse sends a TCP response frame with specified message type (to active connection)
func (nh *NATSInboundHandler) sendTCPResponse(tid uint32, msgType uint8, payload []byte) {
	responseFrame := &config.Frame{
		Type:    msgType,
		TID:     tid,
		Payload: payload,
	}
	
	if err := nh.tcpSender.SendFrame(responseFrame); err != nil {
		nh.logger.Error("failed to send TCP response", "tid", tid, "msg_type", fmt.Sprintf("0x%02x", msgType), "error", err)
	} else {
		nh.logger.Debug("sent TCP response", "tid", tid, "msg_type", fmt.Sprintf("0x%02x", msgType))
	}
}

// sendTCPResponseToConnection sends a TCP response to a specific connection
func (nh *NATSInboundHandler) sendTCPResponseToConnection(connectionID string, tid uint32, msgType uint8, payload []byte) {
	responseFrame := &config.Frame{
		Type:    msgType,
		TID:     tid,
		Payload: payload,
	}
	
	if err := nh.tcpSender.SendFrameToConnection(connectionID, responseFrame); err != nil {
		nh.logger.Error("failed to send TCP response to connection", 
			"connection_id", connectionID,
			"tid", tid, 
			"msg_type", fmt.Sprintf("0x%02x", msgType), 
			"error", err)
	} else {
		nh.logger.Debug("sent TCP response to connection", 
			"connection_id", connectionID,
			"tid", tid, 
			"msg_type", fmt.Sprintf("0x%02x", msgType))
	}
}

// sendTCPErrorResponse sends an error TCP response with specified message type
func (nh *NATSInboundHandler) sendTCPErrorResponse(tid uint32, msgType uint8, errMsg string) {
	errorPayload := []byte(fmt.Sprintf(`{"error":"%s"}`, errMsg))
	nh.sendTCPResponse(tid, msgType, errorPayload)
}

// replyError replies with an error message to NATS
func (nh *NATSInboundHandler) replyError(msg *nats.Msg, errMsg string) {
	if msg.Reply != "" {
		errorResponse := []byte(fmt.Sprintf(`{"error":"%s"}`, errMsg))
		replyPublisher := nh.natsClient.GetReplyPublisher()
		if err := replyPublisher.PublishReply(msg.Reply, errorResponse); err != nil {
			nh.logger.Error("failed to send error reply", "error", err)
		}
		msg.Ack() // ACK the original message as we've handled it (with error)
	}
}

// generateTID는 새로운 Transaction ID를 생성합니다 (thread-safe, sequential).
// atomic.AddUint32를 사용하여 여러 고루틴에서 동시에 호출해도 안전합니다.
//
// 특징:
//   - TID는 1부터 시작하며 0을 반환하지 않음
//   - 매일 자정(날짜 변경)에 카운터가 1로 리셋됨
//   - uint32 overflow 시 1로 재설정됨
//
// 동작:
//   1. 현재 날짜(YYYYMMDD)를 확인
//   2. 날짜가 변경되었으면 카운터를 0으로 리셋 (다음 호출 시 1 반환)
//   3. 카운터를 증가시켜 TID 반환
//   4. TID가 0이면 1로 재설정 (overflow 방지)
func generateTID() uint32 {
	// Get current date in YYYYMMDD format
	now := time.Now()
	currentDate := int32(now.Year()*10000 + int(now.Month())*100 + now.Day())
	
	// Check if date changed and reset counter if needed
	lastDate := atomic.LoadInt32(&lastResetDate)
	if currentDate != lastDate {
		// Try to atomically update the date
		if atomic.CompareAndSwapInt32(&lastResetDate, lastDate, currentDate) {
			// Successfully updated date, reset counter to 0 (next increment will return 1)
			atomic.StoreUint32(&globalTIDCounter, 0)
		}
	}
	
	// Increment and get TID
	tid := atomic.AddUint32(&globalTIDCounter, 1)
	
	// Handle overflow case: never return 0
	if tid == 0 {
		// Overflow occurred (4,294,967,295 + 1 = 0), reset to 1
		atomic.StoreUint32(&globalTIDCounter, 1)
		return 1
	}
	
	return tid
}

// TCPInboundHandler handles incoming TCP frames by dispatching to NATSInboundHandler
type TCPInboundHandler struct {
	logger *slog.Logger
	
	// Dependencies
	natsHandler *NATSInboundHandler
}

// NewTCPInboundHandler creates a new TCP inbound handler
func NewTCPInboundHandler(logger *slog.Logger, natsHandler *NATSInboundHandler) *TCPInboundHandler {
	return &TCPInboundHandler{
		logger:      logger,
		natsHandler: natsHandler,
	}
}

// DispatchRequestFrame dispatches a TCP request frame directly to NATSInboundHandler
func (th *TCPInboundHandler) DispatchRequestFrame(frame *config.Frame) {
	// Validate it's a request type (홀수: 0x05, 0x07, 0x09, 0x0b)
	if !frame.IsRequest() {
		th.logger.Warn("non-request frame passed to handler", 
			"type", fmt.Sprintf("0x%02x", frame.Type), "tid", frame.TID)
		return
	}
	
	// Direct dispatch to NATSInboundHandler (no separate goroutine needed)
	th.natsHandler.HandleTCPRequest(frame)
}