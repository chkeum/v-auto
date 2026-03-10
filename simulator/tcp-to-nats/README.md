# TCP→NATS Simulator

TCP에서 NATS로 가는 흐름을 테스트하는 시뮬레이터입니다.

## Message Structure (4.1)

### Header (8 bytes)
- Byte 1: 0x00 (Extension Bit + Protocol Version + Reserved)
- Byte 2: Message Type (0x05 = Subs-Change-Request)
- Byte 3-4: Body Length (Big Endian)
- Byte 5-8: Transaction Identifier (Big Endian)

### Body
- JSON 형식 (가변 길이)

## Architecture

```
┌──────────────┐    TCP 연결     ┌─────────────┐     NATS      ┌──────────────┐
│  TCP Server  │ ←─────────────  │ tcp-bridge  │ ─────────────→ │ NATS Service │
│  (port 8000) │  (클라이언트로)  │ (클라이언트) │               │ (subscriber) │
└──────────────┘                 └─────────────┘               └──────────────┘
      │                                 │                             │
      │ 1. Listen & Accept              │                             │
      │ 2. HELLO/ACK 핸드셰이크          │                             │
      │ 3. REQUEST 프레임 전송 ─────────→                             │
      │                                 │ 4. internal_req.order 전송 ─→
      │                                 │ ←────── 5. NATS 응답          │
      │ ←─────── 6. RESPONSE 프레임      │                             │
      │ 7. 응답 수신 ✅                   │                             │
```

## Components

### 1. tcp-server.go
- **역할**: TCP 서버 (포트 8000에서 대기)
- **동작**:
  - tcp-bridge의 연결을 수락
  - HELLO/ACK 핸드셰이크 수행
  - 플래그에 따라 주기적으로 REQUEST 프레임 전송
  - RESPONSE 프레임 수신 및 출력

**Command-line Flags:**
- `-send-requests`: REQUEST 메시지 자동 전송 활성화 (기본값: false)
- `-request-interval`: REQUEST 전송 간격 (기본값: 200ms)
- `-request-count`: 전송할 REQUEST 개수 (0 = 무제한, 기본값: 0)
- `-port`: TCP 서버 포트 (기본값: "8000")

### 2. nats-service.go
- **역할**: NATS 서비스 (내부 서비스 시뮬레이션)
- **동작**:
  - `internal_req.order` 주제 구독
  - tcp-bridge에서 전달된 요청 수신
  - 주문 상태 데이터로 응답

## Usage

### 전체 플로우 테스트

```bash
# 1. 시뮬레이터 컴포넌트 시작
cd simulator/tcp-to-nats
./test.sh

# 2. 새 터미널에서 tcp-bridge 시작
cd ../../
./bin/tcp-bridge config.yaml
```

**예상 동작:**
- tcp-bridge가 TCP 서버에 연결
- 핸드셰이크 완료
- TCP 서버가 REQUEST 전송
- tcp-bridge가 NATS로 포워딩
- NATS Service가 응답
- TCP 서버가 RESPONSE 수신

### 개별 컴포넌트 테스트

#### TCP Server만 빌드/실행
```bash
# 빌드
go build -o tcp-server tcp-server.go

# REQUEST 전송 없이 실행 (연결만 유지)
./tcp-server

# REQUEST 자동 전송 활성화 (200ms 간격, 무제한)
./tcp-server -send-requests

# REQUEST 10개만 전송 (1초 간격)
./tcp-server -send-requests -request-count=10 -request-interval=1s

# 다른 포트에서 실행
./tcp-server -port=9000 -send-requests
```

## Frame Protocol

### REQUEST Frame (TCP → tcp-bridge → NATS)
```
Header: [Type:0x01][Length:4bytes][TID:4bytes]
Payload: JSON {
  "message_type": "order",
  "request_id": 1,
  "action": "get_order_status",
  "order_id": 54321,
  "timestamp": 1772187113
}
```

### RESPONSE Frame (NATS → tcp-bridge → TCP)
```
Header: [Type:0x02][Length:4bytes][TID:4bytes]
Payload: JSON {
  "request_id": 1,
  "status": "success",
  "data": {
    "order_id": 54321,
    "status": "shipped",
    "tracking": "TRK123456789",
    ...
  },
  "timestamp": 1772187113,
  "processed_by": "nats-order-service"
}
```

## Configuration

TCP Server는 config.yaml의 conn_0 설정과 일치해야 합니다:

```yaml
# config.yaml
tcp:
  endpoints:
    - address: "127.0.0.1"
      port: 8000      # TCP Server 포트
      priority: 0
```

## Troubleshooting

### tcp-bridge가 연결되지 않음
- TCP Server가 먼저 실행되어 있는지 확인
- 포트 8000이 사용 가능한지 확인: `netstat -an | grep 8000`

### RESPONSE를 받지 못함
- NATS Service가 실행 중인지 확인
- tcp-bridge 로그에서 "internal_req.order" 메시지 확인
- NATS Service 로그에서 요청 수신 확인

### 핸드셰이크 실패
- tcp-bridge 로그에서 "handshake completed" 확인
- TCP Server 로그에서 HELLO/ACK 메시지 확인
