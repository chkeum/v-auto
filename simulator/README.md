# TCP Bridge Simulator

이 디렉터리에는 tcp-bridge를 테스트하기 위한 시뮬레이터 애플리케이션들이 있습니다.

## 메시지 구조 (4.1)

### Header (8 bytes)
- Byte 1: Extension Bit(1) + Protocol Version(2) + Reserved(5) = 0x00
- Byte 2: Message Type (4.1.1.d)
- Byte 3-4: Body Length (Big Endian, 최대 65535)
- Byte 5-8: Transaction Identifier (Big Endian)

### Message Types
| Code | Type                      | 설명                |
|------|---------------------------|---------------------|
| 0x01 | Hello-Request             | 핸드셰이크 요청     |
| 0x02 | Hello-Response            | 핸드셰이크 응답     |
| 0x03 | Ping-Request              | Ping 요청           |
| 0x04 | Ping-Response             | Ping 응답           |
| 0x05 | Subs-Change-Request       | 업무 메시지 (요청)  |
| 0x06 | Subs-Change-Response      | 업무 메시지 (응답)  |
| 0x07 | Subs-Info-Request         | 업무 메시지 (요청)  |
| 0x08 | Subs-Info-Response        | 업무 메시지 (응답)  |
| 0x09 | CellInfo-Noti-Request     | 업무 메시지 (요청)  |
| 0x0a | CellInfo-Noti-Response    | 업무 메시지 (응답)  |
| 0x0b | Subs-Sync-Request         | 업무 메시지 (요청)  |
| 0x0c | Subs-Sync-Response        | 업무 메시지 (응답)  |

### Body
- JSON 형식 (가변 길이)
- Body만 NATS로 전송됨 (Header 제외)

## 시나리오

### 1. NATS → TCP (nats-to-tcp/)

**흐름**: NATS Client → tcp-bridge → TCP Server

```
NATS Client          tcp-bridge          TCP Server
    │                     │                   │
    │──── external_req ───→│                   │
    │                     │─── TCP Request ──→│
    │                     │←── TCP Response ──│
    │←─── NATS Response ──│                   │
```

**구성요소**:
- `nats-client.go`: NATS에 `external_req` subject로 요청을 보내는 클라이언트
- `tcp-server.go`: TCP 포트 8000에서 요청을 받고 응답하는 서버

### 2. TCP → NATS (tcp-to-nats/)

**흐름**: TCP Client → tcp-bridge → NATS Service

```
TCP Client           tcp-bridge          NATS Service  
    │                     │                   │
    │─── TCP Request ────→│                   │
    │                     │── internal_req.* →│
    │                     │←─ NATS Response ──│
    │←── TCP Response ────│                   │
```

**구성요소**:
- `tcp-client.go`: TCP로 tcp-bridge에 요청을 보내는 클라이언트
- `nats-service.go`: NATS `internal_req.*` subject를 구독하고 응답하는 서비스

## 실행 방법

### 준비사항

1. **NATS 서버 실행**:
```bash
# Docker로 실행
docker run -d --name nats-server -p 4222:4222 -p 8222:8222 nats:latest --http_port 8222

# 또는 로컬 설치 후 실행
nats-server --http_port 8222
```

2. **tcp-bridge 실행**:
```bash
cd /home/bigwo/nTels/07.UPM/github/tcp_bridge
./tcp-bridge -config config.yaml
```

### 시나리오 1: NATS → TCP 테스트

1. **TCP Server 실행**:
```bash
cd simulator/nats-to-tcp
go run tcp-server.go
```

2. **NATS Client 실행** (새 터미널):
```bash
cd simulator/nats-to-tcp  
go run nats-client.go
```

**예상 결과**:
- NATS Client가 5초마다 `external_req` subject로 요청 전송
- tcp-bridge가 요청을 TCP Server로 전달
- TCP Server가 사용자 프로필 정보로 응답
- NATS Client가 응답 수신

### 시나리오 2: TCP → NATS 테스트

1. **NATS Service 실행**:
```bash
cd simulator/tcp-to-nats
go run nats-service.go
```

2. **TCP Client 실행** (새 터미널):
```bash
cd simulator/tcp-to-nats
go run tcp-client.go
```

**예상 결과**:
- TCP Client가 3초마다 TCP 요청 전송
- tcp-bridge가 요청을 `internal_req.order` subject로 라우팅
- NATS Service가 주문 상태 정보로 응답
- TCP Client가 응답 수신

## 메시지 라우팅

### NATS → TCP
- Subject: `external_req`
- 모든 요청이 TCP Server로 전달됨

### TCP → NATS  
- `message_type` 필드에 따른 동적 라우팅:
  - `"user"` → `internal_req.user`
  - `"order"` → `internal_req.order` 
  - `"notify"` → `internal_req.notify`
  - 기타 → `internal_req` (기본값)

## 로그 모니터링

각 컴포넌트에서 다음 로그를 확인할 수 있습니다:

**tcp-bridge**:
- NATS 메시지 수신/발송
- TCP 프레임 송수신
- 라우팅 정보

**시뮬레이터들**:
- 요청/응답 페이로드
- 연결 상태
- 처리 시간

## 트러블슈팅

### 연결 실패
- NATS 서버가 4222 포트에서 실행 중인지 확인
- tcp-bridge가 8000 포트에서 실행 중인지 확인
- 방화벽 설정 확인

### 응답 없음
- tcp-bridge 로그에서 에러 확인
- 메시지 라우팅 설정 확인
- 타임아웃 설정 확인 (config.yaml)

### 의존성 에러
```bash
# 각 시뮬레이터 디렉터리에서 실행
go mod init simulator
go mod tidy
```