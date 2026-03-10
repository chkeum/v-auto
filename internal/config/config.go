package config

import (
	"fmt"
	"os"
	"time"

	"gopkg.in/yaml.v2"
)

// Config는 애플리케이션 전체 설정을 나타냅니다.
//
// YAML 파일에서 로드되며, 각 섹션은 다음을 정의합니다:
// - server: 서버 메타데이터 (이름, 버전, 환경, shutdown timeout)
// - tcp: TCP 연결 설정 (다중 endpoint, timeout, frame 크기 등)
// - nats: NATS 설정 (URL, subject, routing, timeout)
// - message_handler: NATS↔TCP 메시지 처리 설정 (timeout, retry)
// - queue: 전송 큐 설정 (현재 미사용, 향후 확장 대비)
// - metrics: Prometheus 메트릭 설정 (HTTP 포트, 경로)
// - logging: 로그 레벨 설정 (debug/info/warn/error)
type Config struct {
	Server     ServerConfig     `yaml:"server"`
	TCP        TCPConfig        `yaml:"tcp"`
	NATS       NATSConfig       `yaml:"nats"`
	MessageHandler MessageHandlerConfig `yaml:"message_handler"`
	Queue      QueueConfig      `yaml:"queue"`
	Metrics    MetricsConfig    `yaml:"metrics"`
	Logging    LoggingConfig    `yaml:"logging"`
}

// ServerConfig contains general server configuration
type ServerConfig struct {
	Name        string        `yaml:"name"`
	Version     string        `yaml:"version"`
	Environment string        `yaml:"environment"`
	ShutdownTimeout time.Duration `yaml:"shutdown_timeout"`
}

// TCPConfig는 TCP 관련 설정을 포함합니다.
//
// 우선순위 기반 다중 연결:
// - Endpoints: priority 값으로 정렬됨 (0=Primary, 1=Secondary, ...)
// - 연결 실패 시 자동으로 다음 우선순위 endpoint로 재연결 시도
// - READY 상태의 가장 높은 우선순위 연결을 활성 연결으로 사용
//
// Frame 프로토콜 (4.1):
// - Header: 8 bytes
//   - Byte 1: Extension Bit(1) + Protocol Version(2) + Reserved(5)
//   - Byte 2: Message Type
//   - Byte 3-4: Body Length (Big Endian, uint16)
//   - Byte 5-8: Transaction Identifier (Big Endian, uint32)
// - MaxFrameSize: 프레임 payload 최대 크기 (NATS max_payload: 1MB)
//
// Handshake:
// - 연결 후 HELLO(0x01) 전송 → ACK(0x02) 대기
// - HandshakeTimeout 내 ACK 미수신 시 연결 종료
//
// Ping/Pong:
// - idle 시 PING(0x03) 전송 → PONG(0x04) 대기
// - PingTimeout 내 PONG 미수신 시 연결 종료 및 재연결
type TCPConfig struct {
	Endpoints []TCPEndpoint `yaml:"endpoints"`  // 외부 서버 endpoint 목록 (priority 기반 정렬)
	
	// Connection settings
	ConnectTimeout    time.Duration `yaml:"connect_timeout"`    // 연결 시도 timeout
	ReadTimeout       time.Duration `yaml:"read_timeout"`       // (미사용) ping-pong으로 연결 상태 관리
	WriteTimeout      time.Duration `yaml:"write_timeout"`      // 단일 write 작업 timeout
	KeepAlive         time.Duration `yaml:"keep_alive"`         // TCP KeepAlive interval
	
	// Frame settings
	MaxFrameSize    int `yaml:"max_frame_size"`    // 최대 frame payload 크기 (프로토콜 스펙: uint16 최대값 65535)
	FrameHeaderSize int `yaml:"frame_header_size"` // Frame header 크기 (8 bytes)
	
	// Hello/ACK handshake
	HandshakeTimeout time.Duration `yaml:"handshake_timeout"` // HELLO/ACK handshake timeout
	SysID           string        `yaml:"sys_id"`            // 접속하는 Peer Name
	BranchName      string        `yaml:"branch_name"`       // 국사명 (SS/DS/BR)
	
	// Ping/Pong
	PingTimeout time.Duration `yaml:"ping_timeout"` // PING 전송 후 PONG 대기 timeout
}

// TCPEndpoint represents a TCP connection endpoint
type TCPEndpoint struct {
	Host     string `yaml:"host"`
	Port     int    `yaml:"port"`
	Priority int    `yaml:"priority"`
}

// NATSConfig contains NATS-related configuration  
type NATSConfig struct {
	URLs           []string      `yaml:"urls"`
	ConnectTimeout time.Duration `yaml:"connect_timeout"`
	
	// Subjects
	ExternalReqSubject string              `yaml:"external_req_subject"` // NATS→TCP subject
	MessageTypeRouting MessageTypeRouting  `yaml:"message_type_routing"` // TCP→NATS Message Type별 subject 매핑
	
	// 하위 호환성을 위해 유지 (사용 안함)
	RoutingRules RoutingRules `yaml:"routing_rules"` // Deprecated: Use MessageTypeRouting instead
	
	// Request settings
	RequestTimeout time.Duration `yaml:"request_timeout"`
}

// MessageTypeRouting defines how to route TCP messages to NATS subjects based on Message Type
type MessageTypeRouting struct {
	NatsToTCP map[string]NatsToTCPRoute `yaml:"nats_to_tcp"` // NATS → TCP 라우팅
	TCPToNATS map[string]TCPToNATSRoute `yaml:"tcp_to_nats"` // TCP → NATS 라우팅
}

// NatsToTCPRoute defines routing info for NATS → TCP direction
type NatsToTCPRoute struct {
	ResponseMsgType string `yaml:"response_msg_type"` // 기대되는 응답 메시지 타입 (hex)
}

// TCPToNATSRoute defines routing info for TCP → NATS direction
type TCPToNATSRoute struct {
	Subject         string `yaml:"subject"`           // NATS subject
	ResponseMsgType string `yaml:"response_msg_type"` // TCP로 보낼 응답 메시지 타입 (hex)
}

// GetSubjectForMessageType returns the NATS subject for given message type (TCP → NATS)
// Returns empty string if no mapping exists
func (m *MessageTypeRouting) GetSubjectForMessageType(msgType uint8) string {
	key := fmt.Sprintf("%02x", msgType)
	if route, exists := m.TCPToNATS[key]; exists {
		return route.Subject
	}
	return ""
}

// GetResponseType returns the response message type for given request type
// Returns 0 if no mapping exists
func (m *MessageTypeRouting) GetResponseType(msgType uint8) uint8 {
	key := fmt.Sprintf("%02x", msgType)
	
	// TCP → NATS 방향 확인
	if route, exists := m.TCPToNATS[key]; exists {
		var respType uint8
		fmt.Sscanf(route.ResponseMsgType, "%02x", &respType)
		return respType
	}
	
	// NATS → TCP 방향 확인
	if route, exists := m.NatsToTCP[key]; exists {
		var respType uint8
		fmt.Sscanf(route.ResponseMsgType, "%02x", &respType)
		return respType
	}
	
	return 0
}

// RoutingRules defines how to route TCP messages to NATS subjects (Deprecated)
type RoutingRules struct {
	Field          string            `yaml:"field"`           // TCP 메시지에서 라우팅 기준 필드
	Mapping        map[string]string `yaml:"mapping"`         // 필드 값 → NATS subject 매핑
	DefaultSubject string            `yaml:"default_subject"` // 매핑되지 않은 경우 기본 subject
}

// GetSubject returns the NATS subject for given field value
func (r *RoutingRules) GetSubject(fieldValue string) string {
	if subject, exists := r.Mapping[fieldValue]; exists {
		return subject
	}
	return r.DefaultSubject
}

// MessageHandlerConfig contains message handler configuration
type MessageHandlerConfig struct {
	Internal MessageHandlerPoolConfig `yaml:"internal"` // NATS→TCP processing
	External MessageHandlerPoolConfig `yaml:"external"` // TCP→NATS processing
}

// MessageHandlerPoolConfig represents configuration for message handling
type MessageHandlerPoolConfig struct {
	Timeout         time.Duration `yaml:"timeout"`          // 전체 처리 timeout (optional, 안전장치)
	ResponseTimeout time.Duration `yaml:"response_timeout"` // 각 시도별 응답 대기 시간
	RetryAttempts   int           `yaml:"retry_attempts"`   // 같은 connection 재시도 횟수
	RetryDelay      time.Duration `yaml:"retry_delay"`      // 재시도 간 대기 시간
}

// QueueConfig contains queue configuration
type QueueConfig struct {
	SendQueueSize int           `yaml:"send_queue_size"`
	SendTimeout   time.Duration `yaml:"send_timeout"`
}

// MetricsConfig contains metrics configuration
type MetricsConfig struct {
	Enabled bool   `yaml:"enabled"`
	Port    int    `yaml:"port"`
	Path    string `yaml:"path"`
}

// LoggingConfig contains logging configuration
type LoggingConfig struct {
	Level  string `yaml:"level"`
	Format string `yaml:"format"`
}

// Address returns the formatted address for TCP endpoint
func (e TCPEndpoint) Address() string {
	return fmt.Sprintf("%s:%d", e.Host, e.Port)
}

// LoadConfig loads configuration from file
func LoadConfig(configPath string) (*Config, error) {
	data, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}
	
	var cfg Config
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("failed to parse config file: %w", err)
	}
	
	// Set defaults
	setDefaults(&cfg)
	
	return &cfg, nil
}

// setDefaults sets default values for configuration
func setDefaults(cfg *Config) {
	if cfg.Server.ShutdownTimeout == 0 {
		cfg.Server.ShutdownTimeout = 30 * time.Second
	}
	
	if cfg.TCP.ConnectTimeout == 0 {
		cfg.TCP.ConnectTimeout = 5 * time.Second
	}
	
	// ReadTimeout: 미사용 (ping-pong으로 연결 상태 관리)
	if cfg.TCP.ReadTimeout == 0 {
		cfg.TCP.ReadTimeout = 30 * time.Second
	}
	
	if cfg.TCP.WriteTimeout == 0 {
		cfg.TCP.WriteTimeout = 30 * time.Second
	}
	
	if cfg.TCP.KeepAlive == 0 {
		cfg.TCP.KeepAlive = 30 * time.Second
	}
	
	if cfg.TCP.MaxFrameSize == 0 {
		cfg.TCP.MaxFrameSize = 65535 // 64KB (프로토콜 스펙: Body Length는 uint16 최대값)
	}
	
	if cfg.TCP.FrameHeaderSize == 0 {
		cfg.TCP.FrameHeaderSize = 8 // 4 bytes length + 4 bytes tid
	}
	
	if cfg.TCP.HandshakeTimeout == 0 {
		cfg.TCP.HandshakeTimeout = 10 * time.Second
	}
	
	if cfg.TCP.PingTimeout == 0 {
		cfg.TCP.PingTimeout = 5 * time.Second
	}
	
	if cfg.NATS.ConnectTimeout == 0 {
		cfg.NATS.ConnectTimeout = 5 * time.Second
	}
	
	if cfg.NATS.RequestTimeout == 0 {
		cfg.NATS.RequestTimeout = 30 * time.Second
	}
	
	if cfg.NATS.ExternalReqSubject == "" {
		cfg.NATS.ExternalReqSubject = "external_req"
	}
	
	// Set default message type routing if not configured
	if cfg.NATS.MessageTypeRouting.NatsToTCP == nil {
		cfg.NATS.MessageTypeRouting.NatsToTCP = map[string]NatsToTCPRoute{
			"05": {ResponseMsgType: "06"}, // Subs-Change
			"09": {ResponseMsgType: "0a"}, // CellInfo-Noti
		}
	}
	if cfg.NATS.MessageTypeRouting.TCPToNATS == nil {
		cfg.NATS.MessageTypeRouting.TCPToNATS = map[string]TCPToNATSRoute{
			"07": {Subject: "tcp.subs.info", ResponseMsgType: "08"}, // Subs-Info
			"0b": {Subject: "tcp.subs.sync", ResponseMsgType: "0c"}, // Subs-Sync
		}
	}
	
	// Set default routing rules if not configured (backward compatibility)
	if cfg.NATS.RoutingRules.Field == "" {
		cfg.NATS.RoutingRules.Field = "message_type"
	}
	if cfg.NATS.RoutingRules.DefaultSubject == "" {
		cfg.NATS.RoutingRules.DefaultSubject = "internal_req"
	}
	if cfg.NATS.RoutingRules.Mapping == nil {
		cfg.NATS.RoutingRules.Mapping = map[string]string{
			"user":   "internal_req.user",
			"order":  "internal_req.order",
			"notify": "internal_req.notify",
		}
	}
	
if cfg.MessageHandler.Internal.Timeout == 0 {
		cfg.MessageHandler.Internal.Timeout = 60 * time.Second
	}

	if cfg.MessageHandler.External.Timeout == 0 {
		cfg.MessageHandler.External.Timeout = 60 * time.Second
	}

	if cfg.MessageHandler.Internal.RetryAttempts == 0 {
		cfg.MessageHandler.Internal.RetryAttempts = 3
	}

	if cfg.MessageHandler.External.RetryAttempts == 0 {
		cfg.MessageHandler.External.RetryAttempts = 3
	}

	if cfg.MessageHandler.Internal.RetryDelay == 0 {
		cfg.MessageHandler.Internal.RetryDelay = 1 * time.Second
	}

	if cfg.MessageHandler.External.RetryDelay == 0 {
		cfg.MessageHandler.External.RetryDelay = 1 * time.Second
	}
	
	if cfg.Queue.SendQueueSize == 0 {
		cfg.Queue.SendQueueSize = 10000
	}
	
	if cfg.Queue.SendTimeout == 0 {
		cfg.Queue.SendTimeout = 5 * time.Second
	}
	
	if cfg.Metrics.Port == 0 {
		cfg.Metrics.Port = 8080
	}
	
	if cfg.Metrics.Path == "" {
		cfg.Metrics.Path = "/metrics"
	}
	
	if cfg.Logging.Level == "" {
		cfg.Logging.Level = "info"
	}
	
	if cfg.Logging.Format == "" {
		cfg.Logging.Format = "json"
	}
}