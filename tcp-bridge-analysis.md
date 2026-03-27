# TCP Bridge 코드 분석

## 프로젝트 개요

- **저장소**: https://github.com/ewyun-ntels/tcp-bridge
- **언어**: Go
- **목적**: TCP ↔ NATS 양방향 메시지 브리지 (고성능, 내결함성 미들웨어)
- **주요 특징**: VIP 페일오버 지원, 우선순위 기반 다중 TCP 연결, NATS Queue Group 부하 분산

---

## 아키텍처 다이어그램

```
External TCP Servers          tcp-bridge                   NATS Cluster
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────────┐
│  Priority 0     │◄───►│  ConnectionMgr   │◄───►│  Queue Group Subs    │
│  Priority 1     │     │  TCP Sender/     │     │  Requester/Reply     │
│  Priority 2...  │     │  Reader          │     └──────────────────────┘
└─────────────────┘     │  InflightMgr     │
                        │  (A: NATS→TCP)   │
                        │  (B: TCP→NATS)   │
                        └──────────────────┘
```

---

## 디렉토리 구조

```
tcp-bridge/
├── cmd/tcp-bridge/        # 메인 진입점 (main.go, App 구조체)
├── internal/
│   ├── config/            # 설정 구조체 및 YAML 로더
│   ├── connection/        # 우선순위 기반 TCP 연결 관리
│   ├── inflight/          # 양방향 요청-응답 추적
│   ├── metrics/           # Prometheus 메트릭
│   ├── nats/              # NATS 클라이언트 (Subscriber, Requester, ReplyPublisher)
│   ├── tcp/               # TCP Sender / Reader
│   └── worker/            # 메시지 핸들러 (NATS↔TCP)
├── config.yaml            # 설정 파일
├── Dockerfile
└── Makefile
```

---

## 핵심 컴포넌트

### 1. ConnectionManager (`internal/connection/manager.go`)

| 항목 | 내용 |
| --- | --- |
| 역할 | 다중 TCP 연결을 우선순위 기반으로 관리 |
| 상태 머신 | `DISCONNECTED → CONNECTING → READY` |
| 재연결 | 5초 주기로 자동 재연결 시도 |
| 페일오버 | `PriorityConnSelector`: 가장 낮은 Priority 번호의 READY 연결 선택 |
| switchback | Primary 복구 시 즉시 Primary로 전환 |
| 핸드셰이크 | JSON 기반 HELLO(0x01) → ACK(0x02) 교환 |
| Ping-Pong | ACK에서 서버가 지정한 `ping_interval`로 idle 감지, `ping_timeout` 초과 시 재연결 |

**연결 생명주기**

```
attemptConnection()
  → net.DialTimeout()
  → performHandshake()  ← ACK에서 PingInterval 수신
  → setState(READY)
  → pingLoop() 시작
  → readLoop() 시작
```

---

### 2. InflightManager (`internal/inflight/manager.go`)

두 개의 독립적인 in-flight 추적기:

| 구분 | 방향 | 키 | 용도 |
| --- | --- | --- | --- |
| **Inflight-A** | NATS → TCP | `TID (uint32)` | RPC 요청-응답 매칭 |
| **Inflight-B** | TCP → NATS | `"connectionID:TID"` | TCP 인바운드 요청 추적 |

- 30초 주기로 만료된 항목 자동 정리
- `Register() → ResponseChan 대기 → HandleResponse()` 흐름

---

### 3. Worker Handlers (`internal/worker/handlers.go`)

#### NATS → TCP 흐름 (NATSInboundHandler)

```
NATS Queue Group 수신
  → TID 생성 (atomic, 일별 리셋)
  → Message Type 결정 (payload의 "msg_type" 필드 또는 기본값 0x05)
  → RPC면 Inflight-A 등록
  → sendAndWaitWithRetry()
      ├─ Priority 0: 3회 재시도 (각 response_timeout 대기)
      ├─ 실패 → Priority 1: 3회 재시도
      └─ 성공: TCP 응답의 payload만 NATS reply 발행 (헤더 제거)
  → msg.Ack()
```

#### TCP → NATS 흐름 (HandleTCPRequest)

```
TCP REQUEST 프레임 수신
  → Message Type으로 NATS subject 결정
      0x07 → "tcp.subs.info"
      0x0b → "tcp.subs.sync"
  → Inflight-B 등록 (추적용)
  → NATS 동기 RPC 호출 (RequestWithTimeoutToSubject)
  → TCP 응답 전송 (요청 connectionID로 직접)
  → Inflight-B 제거
```

---

### 4. TCP Sender / Reader (`internal/tcp/tcp.go`)

| 컴포넌트 | 역할 |
| --- | --- |
| **Sender** | mutex로 frame boundary 보장, 직접 전송 (큐 없음) |
| **Reader** | `SetFrameReadCallback`으로 등록된 콜백 기반 수신 |

**프레임 타입 분류**

| 타입 | 값 | 처리 |
| --- | --- | --- |
| Handshake | 0x01, 0x02 | ConnectionManager에서 처리 |
| Ping/Pong | 0x03, 0x04 | ConnectionManager에서 처리 |
| Request (홀수) | 0x05, 0x07, 0x09, 0x0b | TCP→NATS 흐름 |
| Response (짝수) | 0x06, 0x08, 0x0a, 0x0c | Inflight-A 매칭 |

---

### 5. NATS Client (`internal/nats/client.go`)

| 컴포넌트 | 역할 |
| --- | --- |
| **Subscriber** | QueueSubscribe ("tcp-bridge-workers" 그룹) |
| **ReplyPublisher** | inbox로 응답 발행 |
| **Requester** | `conn.Request()` 기반 동기 RPC |

- 자동 재연결: `MaxReconnects = -1` (무한)
- 재연결 대기: 2초

---

## 프레임 포맷 (8바이트 헤더)

```
┌─────────────────┬─────────────────┬─────────────────────┬──────────────────────┐
│  Byte 1         │  Byte 2         │  Byte 3-4           │  Byte 5-8            │
│  ExtBit(1)+     │  Message Type   │  Body Length        │  Transaction ID      │
│  Version(2)+    │                 │  (Big Endian u16)   │  (Big Endian u32)    │
│  Reserved(5)    │                 │                     │                      │
└─────────────────┴─────────────────┴─────────────────────┴──────────────────────┘
```

---

## 메시지 타입 라우팅

### NATS → TCP (요청 발신, 응답 대기)

| 요청 타입 | 기대 응답 타입 | 설명 |
| --- | --- | --- |
| 0x05 | 0x06 | Subs-Change |
| 0x09 | 0x0a | CellInfo-Noti |

### TCP → NATS (TCP 수신, NATS로 라우팅)

| 요청 타입 | NATS Subject | 응답 타입 | 설명 |
| --- | --- | --- | --- |
| 0x07 | tcp.subs.info | 0x08 | Subs-Info |
| 0x0b | tcp.subs.sync | 0x0c | Subs-Sync |

---

## 애플리케이션 생명주기

### Start 순서

```
metrics → NATS 연결 → InflightMgr → ConnectionMgr → TCP Reader → NATSHandler
```

### Stop 순서 (역순)

```
NATSHandler → TCP Reader → ConnectionMgr → InflightMgr → NATS 연결 → metrics
```

---

## 설정 주요 항목 (`config.yaml`)

| 섹션 | 항목 | 기본값 | 설명 |
| --- | --- | --- | --- |
| tcp | connect_timeout | 5s | TCP 연결 타임아웃 |
| tcp | write_timeout | 30s | 쓰기 타임아웃 |
| tcp | handshake_timeout | 10s | HELLO/ACK 타임아웃 |
| tcp | ping_timeout | 5s | PONG 대기 타임아웃 |
| tcp | max_frame_size | 65535 | 최대 프레임 크기 |
| nats | request_timeout | 30s | NATS RPC 타임아웃 |
| message_handler.internal | response_timeout | 5s | TCP 응답 대기 시간 |
| message_handler.internal | retry_attempts | 3 | 연결당 재시도 횟수 |
| metrics | port | 8080 | Prometheus 메트릭 포트 |

---

## 콜백 연결 구조

```
tcpReader.SetRequestFrameCallback
  → main.handleTCPRequest()
      → metrics.IncTCPFramesReceived("request")
      → tcpHandler.DispatchRequestFrame()
          → natsHandler.HandleTCPRequest()   [TCP→NATS]

tcpReader.SetResponseFrameCallback
  → main.handleTCPResponse()
      → metrics.IncTCPFramesReceived("response")
      → inflightMgr.GetInflightA().HandleResponse()   [NATS→TCP 응답 매칭]
```

---

## 발견된 이슈 및 개선 포인트

| 번호 | 위치 | 내용 | 심각도 |
| --- | --- | --- | --- |
| 1 | `handlers.go:HandleTCPRequest` | Inflight-B의 ResponseChan이 등록은 되지만 실제 사용되지 않음 | 중 |
| 2 | `tcp.go:handleFrame` | TCP→NATS 요청 처리 중 readLoop 블로킹 (동기 NATS 호출) | 중 |
| 3 | `handlers.go:sendAndWaitWithRetry` | `RetryDelay` 설정값이 있으나 실제 재시도 시 사용되지 않음 | 하 |
| 4 | `nats/client.go` | 주석에 "Manual Ack" 명시되어 있으나 Core NATS에서 `msg.Ack()`는 no-op (JetStream 아님) | 중 |
| 5 | `main.go:collectMetrics` | goroutine 생성만 하고 실제 메트릭 수집 로직 없음 (TODO 상태) | 하 |
| 6 | `connection/manager.go` | 앱 시작 후 최초 연결까지 최대 5초 대기 (ticker 초기 지연) | 하 |
