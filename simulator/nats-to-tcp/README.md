# NATS→TCP Simulator

NATS에서 TCP로 가는 흐름을 테스트하는 시뮬레이터입니다.

## Message Structure (4.1)

### TCP Message Header (8 bytes)
- Byte 1: 0x00 (Extension Bit + Protocol Version + Reserved)
- Byte 2: Message Type (0x05 = Subs-Change-Request)
- Byte 3-4: Body Length (Big Endian)
- Byte 5-8: Transaction Identifier (Big Endian)

### NATS Message
- Body만 전송 (JSON 형식)
- `msg_type` 필드로 TCP Message Type 지정 (hex string: "05", "07", etc.)

## Architecture

```
┌──────────────┐     NATS      ┌─────────────┐    TCP 연결     ┌──────────────┐
│ NATS Client  │ ─────────────→ │ tcp-bridge  │ ─────────────→ │  TCP Server  │
│              │ external_req   │             │  (클라이언트로)  │  (port 8000) │
└──────────────┘                └─────────────┘                └──────────────┘
      │                                │                             │
      │ 1. NATS Request 전송           │                             │
      │                                │ 2. Connect & Handshake ────→│
      │                                │ 3. TCP REQUEST 전송 ────────→│
      │                                │ ←────── 4. TCP RESPONSE      │
      │ ←────── 5. NATS Response       │                             │
      │ 6. 응답 수신 ✅                 │                             │
```

## Components

### 1. nats-client.go
- **역할**: NATS 클라이언트 (요청 발송)
- **동작**:
  - `external_req` subject로 요청 전송
  - `msg_type` 필드 포함 (예: "05" = Subs-Change-Request)
  - RPC 스타일 응답 대기

### 2. tcp-server.go
- **역할**: TCP 서버 (포트 8000에서 대기)
- **동작**:
  - tcp-bridge의 연결을 수락
  - HELLO/ACK 핸드셰이크 수행 (Message Type 0x01/0x02)
  - REQUEST 프레임 수신 (Message Type 0x05)
  - RESPONSE 프레임 전송 (Message Type 0x06)
  - PING/PONG 처리 (Message Type 0x03/0x04)

## Usage

### 전체 플로우 테스트

```bash
# 1. Terminal 1: NATS 서버 시작
docker run -d --name nats-server -p 4222:4222 nats:latest

# 2. Terminal 2: TCP Server 시작
cd simulator/nats-to-tcp
go run tcp-server.go

# 3. Terminal 3: tcp-bridge 시작
cd ../../
./bin/tcp-bridge config.yaml

# 4. Terminal 4: NATS Client 시작 (요청 발송)
cd simulator/nats-to-tcp
go run nats-client.go
```

### 빌드

```bash
cd simulator/nats-to-tcp
go build -o tcp-server tcp-server.go
go build -o nats-client nats-client.go

# 실행
./tcp-server &
./nats-client
```

## Message Flow Example

### 1. NATS Client → tcp-bridge
```json
{
  "msg_type": "05",
  "message_type": "user",
  "request_id": 1,
  "action": "get_profile",
  "user_id": 12345,
  "timestamp": 1234567890
}
```

### 2. tcp-bridge → TCP Server (Header + Body)
```
Header (8 bytes):
  [0x00][0x05][0x00 0x6C][0x00 0x00 0x03 0xE8]
   │     │     │          │
   │     │     └─ Body Length = 108
   │     └─ Message Type = 0x05 (Subs-Change-Request)
   └─ Extension/Protocol/Reserved = 0x00

Body (JSON):
  {"message_type":"user","request_id":1,...}
```

### 3. TCP Server → tcp-bridge (Response)
```
Header (8 bytes):
  [0x00][0x06][0x00 0x50][0x00 0x00 0x03 0xE8]
   │     │     │          │
   │     │     └─ Body Length = 80
   │     └─ Message Type = 0x06 (Subs-Change-Response)
   └─ Extension/Protocol/Reserved = 0x00

Body (JSON):
  {"request_id":1,"status":"success",...}
```

### 4. tcp-bridge → NATS Client (Body only)
```json
{
  "request_id": 1,
  "status": "success",
  "data": {...},
  "timestamp": 1234567891,
  "processed_by": "tcp-server"
}
```

## Notes

- **메시지 타입**: NATS 메시지에 `msg_type` 필드 포함 권장
- **TID**: Transaction Identifier는 요청/응답 매칭에 사용
- **Body만 전송**: NATS에는 JSON Body만 전송됨 (Header 제외)
- **Ping**: 30초 idle time 후 자동 전송 (Message Type 0x03/0x04)
