# v-auto 통합 기술 마스터 가이드 (Definitive Master Guide)

`v-auto`는 OpenShift Virtualization 환경에서 가상 머신(VM) 및 관련 자원(Disk, Network, Secret) 배포를 자동화하는 기술지원팀 전용 마스터 도구입니다. 본 문서는 도구의 사용법부터 YAML 설계 원칙까지 모든 내용을 담고 있습니다.

---

## 1. CLI 명령어 및 파라미터 (CLI Reference)

모든 명령은 `python3 vm_manager.py [PROJECT] [SPEC] [ACTION]` 형식을 따릅니다.

### 1-1. 핵심 액션 (Core Actions)
- **`deploy`**: 설계도(YAML)를 기반으로 인프라를 생성합니다. (이미 존재 시 `[SKIPPED]`)
- **`delete`**: 관련 자원을 안전하게 일괄 삭제합니다. (라벨 기반 정밀 삭제)
- **`status`**: 배포 현황, IP 주소, 디스크 복제율, PVC 상태, 최근 **Warning 이벤트**를 통합 진단합니다.

### 1-2. 주요 플래그 (Primary Flags)
- **`--replicas N`**: YAML 설정을 무시하고 일시적으로 N대의 복제본을 배포합니다.
- **`--target NAME`**: 특정 인스턴스(예: `web-02`)만 핀포인트로 배포/삭제/조회합니다. 이름의 번호를 읽어 IP를 자동 계산합니다.

---

## 2. 계정 및 인증 심화 가이드 (Advanced Auth)

### 2-1. 다중 계정 생성 및 패스워드 주입
실무에서는 관리용 계정과 서비스용 계정을 동시에 생성해야 할 때가 많습니다. `v-auto`는 복수의 변수를 감지하여 각각 입력받습니다.

```yaml
# spec.yaml 예시
cloud_init: |
  #cloud-config
  users:
    - name: admin-user
      passwd: {{ password }}      # 첫 번째 입력 (Password for admin-user)
    - name: guest-user
      passwd: {{ guest_password }} # 두 번째 입력 (Password for guest_password)
      sudo: False
```

### 2-2. 동적 사용자 감지 로직
- 툴은 `{{ variable }}` 형식을 찾아내어 실행 시 사용자에게 값을 묻습니다.
- `auth.username`을 지정하면 해당 이름이 프롬프트 가이드로 사용됩니다.

---

## 3. 네트워크 심화 설계 (Multi-NIC & IPAM)

### 3-1. 다중 NIC(랜카드) 구성 예시
서비스망과 관리망을 분리하는 전형적인 구성입니다.

```yaml
# config.yaml (카탈로그 정의)
networks:
  service-net: { bridge: br-ex, ipam: { range: "10.10.10.0/24" } }
  mgmt-net:    { bridge: br-int, ipam: { range: "192.168.1.0/24" } }

# spec.yaml (사용 설정)
networks:
  - service-net  # eth0 (통상 기본 게이트웨이 할당)
  - mgmt-net     # eth1
```

### 3-2. 혼합 IP 할당 (Static + DHCP)
- **eth0 (Static)**: `range` 설정을 통해 `.101` 등 고정 IP 할당.
- **eth1 (DHCP)**: 카탈로그의 `ipam` 설정을 비워두면 인프라 DHCP를 사용하도록 동작.

---

## 4. 스케줄링 및 선호도 (Scheduling & Affinity)

### 4-1. 다중 `nodeSelector` (AND 조건)
```yaml
node_selector:
  region: "seoul"
  hw-type: "high-mem"
  storage: "local-ssd" # 세 라벨이 모두 일치하는 노드에만 배치됨
```

### 4-2. 복합 Affinity (랙 단위 분산 등)
```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: "kubernetes.io/hostname"
          operator: "NotIn"
          values: ["node-bad-01"] # 특정 노드 제외
```

---

## 5. YAML 풀 사양 상세 레퍼런스 (Full YAML Spec)

| 필드명 | 상세 설명 및 설정 예시 | 필수 |
| :--- | :--- | :--- |
| `name_prefix` | 생성될 VM 이름의 접두사. (예: `web` -> `web-01`) | **Yes** |
| `replicas` | 복제본 수. (예: `3`) | No (1) |
| `cpu` | 가상 CPU 코어 수. (예: `4`) | **Yes** |
| `memory` | 메모리 크기. (예: `8Gi`, `512Mi`) | **Yes** |
| `image_url` | 원본 이미지 주소. (예: `http://10.0.0.1/rhel9.qcow2`) | **Yes** |
| `disk_size` | 할당할 디스크 용량. (예: `100Gi`) | **Yes** |
| `storage_class` | K8s 스토리지 규격. (예: `ocs-storagecluster-ceph-rbd`) | No |
| `networks` | 사용할 네트워크 이름 리스트. (예: `['net1', 'net2']`) | No |
| `node_selector` | 노드 라벨 필터 (Key-Value 딕셔너리). | No |
| `affinity` | K8s 표준 Affinity 설정 (JSON/Dict 구조). | No |
| `cloud_init` | Cloud-Config 스크립트 본문. (예: `#cloud-config ...`) | No |

---

## 6. 기술지원팀 실무 팁 (Expert Tips)

1.  **IP 계산 일괄 확인**: `deploy --replicas 5`를 치고 `dry-run` 화면에서 각 인스턴스에 주입될 예상 IP(.101~.105)를 미리 확인할 수 있습니다.
2.  **핀포인트 복구 활용**: 전체 10대 중 `db-03`만 문제가 생겼다면, 전체를 지우지 말고 `deploy --target db-03`을 사용하여 해당 번호와 IP를 그대로 살려내십시오.
3.  **이벤트 히스토리**: `status`에서 보이는 이벤트는 최근 15줄을 보여주며, **Warning**이 발생하면 해당 노드의 리소스 부족이나 스케줄링 실패 사유를 즉시 파악할 수 있습니다.

---
*Developed for excellence in OpenShift Virtualization delivery by Technical Support Team.*
