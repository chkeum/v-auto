# TCP-Bridge 소스 분석 및 보완 사항 보고서

## 1. 보안 취약점

### 1.1 JSON Injection 위험 [심각도: 높음]
- **위치**: `worker/handlers.go:534`, `nats/client.go:278`
- **문제**: `fmt.Sprintf(`{"error":"%s"}`, errMsg)` 형태로 JSON을 구성하면, errMsg에 `"`가 포함될 경우 JSON이 깨지거나 injection 공격이 가능
- **권장**: `json.Marshal`을 사용하여 안전하게 JSON 생성

```go
// Before (취약)
errorPayload := []byte(fmt.Sprintf(`{"error":"%s"}`, errMsg))

// After (안전)
errorResp := map[string]string{"error": errMsg}
errorPayload, _ := json.Marshal(errorResp)
```

## 2. 동시성 / Race Condition 이슈

### 2.1 `cleanupConnection` 이중 호출로 인한 panic 위험 [심각도: 높음]
- **위치**: `connection/manager.go:684-698`
- **문제**: `readLoop`의 defer와 `pingLoop`의 timeout 핸들링에서 동시에 `cleanupConnection()`을 호출할 수 있음. `pingDone` 채널을 두 번 close하면 panic 발생
- **권장**: `sync.Once`를 사용하거나, `pingDone`을 nil 체크 전에 별도 변수로 보관

```go
// 권장 수정안
type ConnMgr struct {
    // ...
    cleanupOnce sync.Once
}

func (c *ConnMgr) cleanupConnection() {
    c.cleanupOnce.Do(func() {
        c.mu.Lock()
        defer c.mu.Unlock()
        if c.pingDone != nil {
            close(c.pingDone)
            c.pingDone = nil
        }
        if c.conn != nil {
            c.conn.Close()
            c.conn = nil
        }
    })
}
```

### 2.2 `generateTID()` 날짜 리셋 Race Condition [심각도: 중간]
- **위치**: `worker/handlers.go:563-589`
- **문제**: 두 goroutine이 동시에 날짜 변경을 감지하면, CAS 성공한 쪽만 counter를 리셋하지만, 다른 쪽은 리셋 전의 counter를 읽을 수 있음. 실질적 영향은 낮지만 TID가 일시적으로 비순차적일 수 있음
- **권장**: mutex 기반 리셋으로 변경하거나, 현재 수준 허용 (문서화)

### 2.3 `DispatchRequestFrame` 동기 실행 [심각도: 중간]
- **위치**: `worker/handlers.go:608-618`
- **문제**: `DispatchRequestFrame`이 `HandleTCPRequest`를 동기적으로 호출하여, NATS 요청 완료까지 TCP `readLoop`가 블로킹됨. 해당 연결의 다른 수신 메시지 처리가 지연됨
- **권장**: 별도 goroutine으로 비동기 처리

```go
func (th *TCPInboundHandler) DispatchRequestFrame(frame *config.Frame) {
    if !frame.IsRequest() {
        return
    }
    go th.natsHandler.HandleTCPRequest(frame)  // 비동기 처리
}
```

## 3. 설정 검증 부재

### 3.1 Config Validation 없음 [심각도: 중간]
- **위치**: `config/config.go:209-224`
- **문제**: 설정 파일 로드 시 필수 값 검증이 없음
  - Endpoint가 0개일 때 에러 없이 시작
  - Port 범위 검증 없음 (0, 음수, 65535 초과)
  - NATS URL 유효성 검증 없음
  - `ResponseTimeout` 기본값 미설정 (`MessageHandler.Internal/External.ResponseTimeout`)
- **권장**: `Validate()` 메서드 추가

```go
func (cfg *Config) Validate() error {
    if len(cfg.TCP.Endpoints) == 0 {
        return fmt.Errorf("at least one TCP endpoint is required")
    }
    for _, ep := range cfg.TCP.Endpoints {
        if ep.Port <= 0 || ep.Port > 65535 {
            return fmt.Errorf("invalid port %d for endpoint %s", ep.Port, ep.Host)
        }
    }
    if len(cfg.NATS.URLs) == 0 {
        return fmt.Errorf("at least one NATS URL is required")
    }
    return nil
}
```

## 4. 리소스 / 성능 이슈

### 4.1 Context 미전파 [심각도: 중간]
- **위치**: `connection/manager.go:140-153`
- **문제**: `ConnMgr.Start(ctx)`이 전달받은 ctx를 무시하고 자체 context 사용. 부모 context 취소 시 하위 연결이 종료되지 않을 수 있음
- **권장**: 부모 context를 기반으로 child context 생성

```go
func NewConnMgr(...) *ConnMgr {
    // Start()에서 ctx를 받아 child context 생성하도록 변경
}

func (c *ConnMgr) Start(ctx context.Context) error {
    c.ctx, c.cancel = context.WithCancel(ctx) // 부모 ctx 기반
    go c.connectionLoop()
    return nil
}
```

### 4.2 Info 레벨 과다 로깅 [심각도: 낮음]
- **위치**: `connection/manager.go:608-616`
- **문제**: 모든 TCP 프레임 수신을 Info 레벨로 로깅. 프로덕션 환경에서 대량 트래픽 시 로그 부하 발생
- **권장**: Debug 레벨로 변경, 에러/상태변경만 Info 유지

### 4.3 Metrics 미수집 [심각도: 낮음]
- **위치**: `cmd/tcp-bridge/main.go:270-277`
- **문제**: `collectMetrics()` goroutine의 ticker 루프가 비어 있음. Inflight 건수, 큐 사이즈 등이 Prometheus에 보고되지 않음
- **권장**: 주기적으로 inflight entry 수 등을 메트릭에 반영

### 4.4 미사용 SendQueue 패키지 [심각도: 낮음]
- **위치**: `internal/queue/queue.go`
- **문제**: 전체 소스에서 queue 패키지가 사용되지 않음 (Direct Transmission 방식으로 변경됨). 불필요한 코드 잔존
- **권장**: 사용 계획이 없으면 제거, 있으면 주석으로 명시

## 5. 코드 품질

### 5.1 미사용 의존성 [심각도: 낮음]
- **위치**: `go.mod:7`
- **문제**: `github.com/google/uuid`가 import되어 있으나 소스에서 사용하지 않음
- **권장**: `go mod tidy` 실행 또는 수동 제거

### 5.2 바이너리 파일 Git 커밋 [심각도: 낮음]
- **위치**: `tcp-bridge` (14MB), `simulator/*/tcp-server`, `simulator/*/nats-client`
- **문제**: 컴파일된 바이너리가 Git에 포함되어 저장소 크기 증가
- **권장**: `.gitignore`에 바이너리 추가, Git history에서 제거

### 5.3 Graceful Shutdown 개선 [심각도: 낮음]
- **위치**: `cmd/tcp-bridge/main.go:91-92`
- **문제**: 두 번째 SIGINT/SIGTERM 시 강제 종료 미지원. Shutdown이 오래 걸릴 때 사용자가 강제 종료할 수 없음
- **권장**: 두 번째 시그널 시 `os.Exit(1)` 호출

### 5.4 테스트 코드 부재 [심각도: 중간]
- **문제**: 전체 프로젝트에 단위 테스트(`_test.go`)가 없음
- **권장**: 핵심 컴포넌트별 테스트 작성
  - `config`: YAML 파싱, 기본값, 검증
  - `types`: Frame Serialize/Deserialize
  - `inflight`: Register/HandleResponse/Cleanup
  - `worker`: TID 생성, 메시지 타입 결정

## 6. 프로토콜 / 비즈니스 로직

### 6.1 Deprecated RoutingRules 공존 [심각도: 낮음]
- **위치**: `config/config.go:155-168`, `worker/handlers.go:423-451`
- **문제**: `RoutingRules` (Deprecated)와 `MessageTypeRouting`이 동시에 존재. 설정 혼란 가능
- **권장**: 마이그레이션 완료 후 Deprecated 코드 제거 로드맵 수립

### 6.2 재시도 시 동일 TID 재사용 [심각도: 중간]
- **위치**: `worker/handlers.go:244-329`
- **문제**: 재시도 시 동일한 TID로 프레임을 다시 전송. 서버 측에서 중복 요청으로 처리하거나, 이전 요청의 응답이 새 요청의 응답으로 잘못 매칭될 가능성
- **권장**: 재시도마다 새로운 TID 생성, 또는 Inflight에서 이전 entry 교체

---

## 우선순위 요약

| 우선순위 | 항목 | 심각도 |
|---------|------|--------|
| 1 | cleanupConnection 이중 호출 panic | 높음 |
| 2 | JSON Injection 취약점 | 높음 |
| 3 | DispatchRequestFrame 동기 블로킹 | 중간 |
| 4 | Config Validation 부재 | 중간 |
| 5 | Context 미전파 | 중간 |
| 6 | 재시도 시 TID 재사용 | 중간 |
| 7 | 테스트 코드 부재 | 중간 |
| 8 | Info 레벨 과다 로깅 | 낮음 |
| 9 | Metrics 미수집 | 낮음 |
| 10 | 미사용 코드/의존성 정리 | 낮음 |
