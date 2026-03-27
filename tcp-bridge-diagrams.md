# TCP Bridge 로직 다이어그램

---

## 1. 전체 시스템 아키텍처

```mermaid
graph TB
    subgraph External["외부 TCP 서버"]
        TCP0["TCP Server\nPriority 0 (Primary)"]
        TCP1["TCP Server\nPriority 1 (Secondary)"]
        TCP2["TCP Server\nPriority 2 (Tertiary)"]
    end

    subgraph Bridge["tcp-bridge"]
        CM["ConnectionManager\n(우선순위 기반 연결 관리)"]
        Sender["TCP Sender\n(mutex 직접 전송)"]
        Reader["TCP Reader\n(콜백 기반 수신)"]
        NATSHandler["NATSInboundHandler\n(NATS→TCP)"]
        TCPHandler["TCPInboundHandler\n(TCP→NATS)"]
        InflightA["Inflight-A\nNATS→TCP 요청 추적\n(key: TID)"]
        InflightB["Inflight-B\nTCP→NATS 요청 추적\n(key: connID:TID)"]
        Metrics["Prometheus Metrics\n:8080/metrics"]
    end

    subgraph NATS["NATS Cluster"]
        QSub["Queue Group Subscriber\n(tcp-bridge-workers)"]
        Req["Requester\n(RPC)"]
        Reply["ReplyPublisher\n(inbox reply)"]
        Subject1["tcp.subs.info"]
        Subject2["tcp.subs.sync"]
    end

    TCP0 <-->|"HELLO/ACK\nPing/Pong\nFrames"| CM
    TCP1 <--> CM
    TCP2 <--> CM
    CM --> Sender
    CM --> Reader
    Reader -->|"REQUEST 프레임"| TCPHandler
    Reader -->|"RESPONSE 프레임"| InflightA
    TCPHandler --> NATSHandler
    NATSHandler --> Sender
    NATSHandler --> InflightA
    NATSHandler --> InflightB
    QSub -->|"메시지 수신"| NATSHandler
    NATSHandler --> Reply
    Req <-->|"RPC"| Subject1
    Req <-->|"RPC"| Subject2
    NATSHandler --> Req
```

---

## 2. 연결 상태 머신 (ConnectionManager)

```mermaid
stateDiagram-v2
    [*] --> DISCONNECTED : 초기 상태

    DISCONNECTED --> CONNECTING : 5초 주기 ticker\nattemptConnection()
    CONNECTING --> DISCONNECTED : net.DialTimeout 실패
    CONNECTING --> CONNECTING : Handshake 실패\n→ CONNECT_FAILED → 재시도
    CONNECTING --> READY : Handshake 성공\n(HELLO → ACK)

    READY --> DISCONNECTED : readLoop 오류\n(연결 끊김)
    READY --> DISCONNECTED : pingTimeout 초과\n(PONG 미수신)

    note right of READY
        pingLoop 실행 중
        readLoop 실행 중
        PriorityConnSelector에 등록
    end note

    note right of DISCONNECTED
        5초 후 자동 재연결 시도
        PriorityConnSelector에서 제외
    end note
```

---

## 3. 우선순위 기반 Failover

```mermaid
graph LR
    subgraph Selector["PriorityConnSelector"]
        direction TB
        P0["Priority 0\nconn_0\n🟢 READY"]
        P1["Priority 1\nconn_1\n🟡 DISCONNECTED"]
        P2["Priority 2\nconn_2\n🟢 READY"]
        Active["Active Connection\n→ conn_0"]
    end

    P0 -->|"가장 낮은 Priority\n= 최우선 선택"| Active

    subgraph Failover["P0 장애 발생 시"]
        direction TB
        P0F["Priority 0\nconn_0\n🔴 DISCONNECTED"]
        P1F["Priority 1\nconn_1\n🟡 DISCONNECTED"]
        P2F["Priority 2\nconn_2\n🟢 READY"]
        ActiveF["Active Connection\n→ conn_2"]
    end

    P2F -->|"다음 READY 연결 선택"| ActiveF

    subgraph Recovery["P0 복구 시 (Switchback)"]
        direction TB
        P0R["Priority 0\nconn_0\n🟢 READY"]
        P2R["Priority 2\nconn_2\n🟢 READY"]
        ActiveR["Active Connection\n→ conn_0 (복귀)"]
    end

    P0R -->|"더 낮은 Priority 우선"| ActiveR
```

---

## 4. NATS → TCP 메시지 흐름

```mermaid
sequenceDiagram
    participant NATS
    participant Handler as NATSInboundHandler
    participant InflightA as Inflight-A
    participant Sender as TCP Sender
    participant TCP as TCP Server

    NATS->>Handler: msg (subject, payload, reply)
    Handler->>Handler: generateTID() [atomic]
    Handler->>Handler: determineMessageType(payload)
    Handler->>InflightA: Register(tid, replySubject, deadline)

    loop Priority 0,1,2... × RetryAttempts(3)
        Handler->>Sender: conn[priority].Write(frame)
        alt 전송 성공
            TCP-->>InflightA: handleTCPResponse(frame)
            InflightA-->>Handler: ResponseChan ← frame
            Handler->>NATS: PublishReply(replySubject, payload)
            Handler->>NATS: msg.Ack()
            Note over Handler: 성공 종료
        else response_timeout (5s) 초과
            Handler->>Handler: 즉시 재시도
        end
    end

    alt 모든 시도 실패
        Handler->>InflightA: Remove(tid)
        Handler->>NATS: PublishReply(error)
        Handler->>NATS: msg.Ack()
    end
```

---

## 5. TCP → NATS 메시지 흐름

```mermaid
sequenceDiagram
    participant TCP as TCP Server
    participant Reader as TCP Reader
    participant Handler as NATSInboundHandler
    participant InflightB as Inflight-B
    participant NATS

    TCP->>Reader: REQUEST 프레임 (0x07 or 0x0b)
    Reader->>Reader: handleFrame() - 타입 분류
    Reader->>Handler: DispatchRequestFrame(frame)
    Handler->>Handler: GetSubjectForMessageType(0x07)\n→ "tcp.subs.info"
    Handler->>InflightB: Register(tid, connectionID, deadline)

    Handler->>NATS: RequestWithTimeoutToSubject("tcp.subs.info", payload)
    Note over Handler,NATS: 동기 블로킹 호출

    NATS-->>Handler: response payload
    Handler->>Handler: responseType = 0x07+1 = 0x08
    Handler->>TCP: SendFrameToConnection(connID, 0x08, response)
    Handler->>InflightB: Remove(connID, tid)
```

---

## 6. 핸드셰이크 프로토콜

```mermaid
sequenceDiagram
    participant Bridge as tcp-bridge
    participant Server as TCP Server

    Bridge->>Server: HELLO 프레임 (0x01)\n{ sys_id, branch_name }

    alt 핸드셰이크 성공
        Server-->>Bridge: ACK 프레임 (0x02)\n{ code:0, sys_id, ping_interval }
        Bridge->>Bridge: pingInterval 저장\nRead/Write Deadline 해제
        Bridge->>Bridge: setState(READY)
        Bridge->>Bridge: pingLoop() 시작
    else 핸드셰이크 실패
        Server-->>Bridge: ACK 프레임 (0x02)\n{ code:!=0, cause }
        Bridge->>Bridge: cleanupConnection()\nsetState(CONNECT_FAILED)
    end
```

---

## 7. Ping-Pong Keep-Alive

```mermaid
sequenceDiagram
    participant Loop as pingLoop (1초 체크)
    participant Bridge as tcp-bridge
    participant Server as TCP Server

    loop 매 1초마다
        Loop->>Loop: idleTime = now - lastActivityTime

        alt idleTime >= pingInterval AND !awaitingPong
            Loop->>Bridge: sendPing()
            Bridge->>Server: PING 프레임 (0x03)
            Loop->>Loop: awaitingPong = true
        end

        alt awaitingPong AND idleTime > pingTimeout
            Loop->>Bridge: cleanupConnection()
            Bridge->>Bridge: setState(DISCONNECTED)
            Note over Bridge: 재연결 트리거
        end
    end

    Server-->>Bridge: PONG 프레임 (0x04)
    Bridge->>Loop: awaitingPong = false
```

---

## 8. 프레임 포맷

```mermaid
packet-beta
    0-0: "ExtBit (1)"
    1-2: "ProtocolVer (2)"
    3-7: "Reserved (5)"
    8-15: "Message Type (8)"
    16-31: "Body Length (16, Big Endian)"
    32-63: "Transaction ID (32, Big Endian)"
    64-127: "Payload (가변 길이, 최대 65535 bytes)"
```

---

## 9. 애플리케이션 시작/종료 순서

```mermaid
graph LR
    subgraph Start["▶ Start 순서"]
        S1["1. Metrics\n서버 시작"] --> S2["2. NATS\n연결"] --> S3["3. InflightMgr\n시작"] --> S4["4. ConnectionMgr\n시작"] --> S5["5. TCP Reader\n시작"] --> S6["6. NATSHandler\n구독 시작"]
    end

    subgraph Stop["⏹ Stop 순서 (역순)"]
        E1["1. NATSHandler\n구독 해제"] --> E2["2. TCP Reader\n중지"] --> E3["3. ConnectionMgr\n중지"] --> E4["4. InflightMgr\n중지"] --> E5["5. NATS\n연결 해제"] --> E6["6. Metrics\n서버 중지"]
    end
```

---

## 10. TID 생성 로직

```mermaid
flowchart TD
    A["generateTID() 호출"] --> B{"날짜 변경됨?\n(YYYYMMDD 비교)"}
    B -->|Yes| C["CAS로 날짜 업데이트\nglobalTIDCounter = 0"]
    B -->|No| D["atomic.AddUint32\n+1 증가"]
    C --> D
    D --> E{"tid == 0?\n(uint32 overflow)"}
    E -->|Yes| F["globalTIDCounter = 1\nreturn 1"]
    E -->|No| G["return tid"]
```
