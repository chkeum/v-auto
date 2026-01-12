# v-auto 통합 기술 마스터 가이드 (Definitive Master Guide)

`v-auto`는 OpenShift Virtualization 환경에서 가상 머신(VM) 및 관련 자원(Disk, Network, Secret) 배포를 자동화하는 기술지원팀 전용 마스터 도구입니다. 본 문서는 도구의 사용법부터 YAML 설계 원칙까지 모든 내용을 담고 있습니다.

---

## 1. CLI 명령어 및 실행 결과 (CLI Reference & Output)

모든 명령은 `python3 vm_manager.py [PROJECT] [SPEC] [ACTION]` 형식을 따릅니다.

### 1-1. 핵심 액션 (Core Actions)
- **`deploy`**: 설계도(YAML)를 기반으로 인프라를 생성합니다.
- **`delete`**: 관련 자원을 라벨 기반으로 안전하게 일괄 삭제합니다.
- **`status`**: 배포 현황, IP 주소, 디스크 복제율, 이벤트 등을 통합 진단합니다.

### 1-2. CLI 실행 결과 예시 (Sample Outputs)

#### [deploy] 실행 시
```text
=== 배포 계획 (Dry-run) ===
Project: samsung, Spec: web, Replicas: 2
- VM 1: web-01 (IP: 10.10.10.101)
- VM 2: web-02 (IP: 10.10.10.102)

Proceed? (y/n): y

[SUCCESS] Secret: web-cloud-init-01 생성 완료
[SUCCESS] DataVolume: web-root-disk-01 생성 완료
[SUCCESS] VM: web-01 생성 완료
... (이후 자동 status 요약 출력)
```

#### [status] 실행 시
```text
=== v-auto Deployment Status (samsung/web) ===

RESOURCE  NAME    PHASE    ADDRESS       PROGRESS  AGE
VM        web-01  Running  10.10.10.101  100%      2m
VM        web-02  Starting 10.10.10.102  45%       1m

IP Address Summary:
- web-01: 10.10.10.101 (nic0/svc-net)
- web-02: 10.10.10.102 (nic0/svc-net)

Recent Events (Warning only):
- 2m ago: [Warning] FailedScheduling: node(s) had insufficient memory (web-02)
```

---

## 2. 지능형 계정 및 보안 메커니즘 (Intelligent Auth Chain)

`v-auto`는 사용자의 개입을 최소화하면서도 강력한 보안을 유지하기 위해 다음 워크플로우를 따릅니다.

### 2-1. 동적 계정 감지 워크플로우
1.  **스캔(Discovery)**: 툴이 `spec.yaml` 내 `cloud_init` 섹션을 분석하여 `{{ password }}`와 같은 변수 패턴을 자동으로 찾아냅니다.
2.  **질의(Prompting)**: 실행 시 터미널에서 사용자에게 해당 계정의 패스워드를 묻습니다. (입력 시 보안을 위해 화면에 표시되지 않음)
3.  **렌더링(Rendering)**: 입력된 패스워드를 템플릿의 변수 자리에 안전하게 치환합니다.

### 2-2. Secret 저장 및 수명 주기
- **저장**: 렌더링된 전체 설정값은 **`[VM이름]-cloud-init`** 이름의 Kubernetes Secret에 Base64로 암호화되어 저장됩니다.
- **연결**: 생성된 VM은 이 Secret을 기동 시점에 참조하여 운영체제 내부에 계정을 생성합니다.
- **파기**: `delete` 명령 수행 시, 툴은 VM뿐만 아니라 해당 VM에 귀속된 Secret까지 라벨 추적을 통해 완벽하게 제거합니다.

---

## 3. 네트워크 및 다중 NIC 설계 (Network & Multi-NIC)

### 3-1. 지능형 IPAM (자동 계산)
`config.yaml`에 `range`를 지정하면 툴이 다음과 같이 IP를 자동 할당합니다.
- **수식**: `네트워크 주소 + 101 + 인덱스`
- **예시**: `10.10.10.0/24` -> `web-01`(.101), `web-02`(.102)

### 3-2. 다중 NIC 구성 예제
```yaml
# config.yaml (네트워크 카탈로그)
networks:
  svc-net:  { bridge: br-ex, ipam: { range: "10.10.10.0/24" } }
  mgmt-net: { nad_name: "existing-mgmt-nad" } # 외부 NAD 참조 모드

# spec.yaml (사용 설정)
networks:
  - svc-net   # eth0
  - mgmt-net  # eth1
```

---

## 4. 스토리지 상세 설계 (Storage & DataVolume)

OpenShift Virtualization은 `DataVolume`을 통해 디스크 이미지를 관리합니다.

### 4-1. 이미지 스트리밍 및 PVC 관리
- **DataVolume**: 외부 HTTP/S 소스에서 이미지를 가져와 PVC를 생성합니다.
- **Status 진단**: `status` 실행 시 보이는 `PROGRESS`는 바로 이 DataVolume의 복제 진행률입니다.
- **StorageClass 우선순위**: `spec.yaml` > `config.yaml` 순으로 적용됩니다.

### 4-2. 설정 예시
```yaml
# spec.yaml
storage_class: "ocs-storagecluster-ceph-rbd" # 영구 저장소 타입
disk_size: "100Gi"                          # VM에 할당할 실제 공간
image_url: "http://10.0.0.1/rhel9.qcow2"    # 원본 이미지 소스
```

---

## 5. 고급 스케줄링 (Node Selector & Affinity)

VM이 기동될 노드의 물리적 위치와 하드웨어 특성을 정밀하게 제어합니다.

### 5-1. Node Selector (하드 제약)
모든 라벨이 일치하는 노드에만 VM이 배치됩니다.
```yaml
node_selector:
  region: "seoul-zone-1"
  hw-type: "high-mem"
  gpu: "enabled"
```

### 5-2. Node Affinity (유연한 규칙)
표준 Kubernetes 문법을 사용하여 선호도(Soft)나 필수(Hard) 조건을 설정합니다.
```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: "rack"
          operator: "In"
          values: ["rack-01", "rack-02"]
```

---

## 6. 내부 템플릿 엔진 (The Template System)

`v-auto`는 **Jinja2** 엔진을 사용하여 YAML 설계도를 실제 Kubernetes 리소스로 변환합니다.

### 6-1. 주요 템플릿 파일
- **`vm_template.yaml`**: CPU/Mem/Disk/Network/Affinity가 조합되는 핵심 템플릿.
- **`datavolume_template.yaml`**: 이미지 복제 및 PVC 정의.
- **`nad_template.yaml`**: 대역별 L2 브리지 네트워크 정의.
- **`secret_template.yaml`**: Cloud-Init 설정 및 패스워드 주입.

### 6-2. 기술지원팀을 위한 템플릿 수정 가이드
특정 환경에서 특수한 어노테이션이나 설정을 추가해야 할 경우, `templates/` 하위의 파일들을 수정하면 배포되는 모든 VM에 즉시 반영됩니다.

---

## 7. YAML 풀 레퍼런스 (Full Specification)

| 구분 | 필드 | 상세 설명 및 예시 |
| :--- | :--- | :--- |
| **기본 정보** | `name_prefix` | VM 이름의 시작점. (예: `web`) |
| | `replicas` | 생성할 대수. (예: `5`) |
| **자원 사양** | `cpu` / `memory` | 코어 및 메모리 크기. (예: `4`, `8Gi`) |
| | `disk_size` | OS 디스크 용량. (예: `100Gi`) |
| **이미지** | `image_url` | 원본 이미지 HTTP 경로. |
| **인프라** | `storage_class` | 스토리지 규격 (Ceph-RBD 등). |
| | `networks` | 사용할 네트워크 리스트. |
| **스케줄링** | `node_selector` | 노드 물리적 위치 지정 (Dict). |
| | `affinity` | 가용성 및 선호도 규칙 (Dict). |
| **기타** | `cloud_init` | 초기 설정 스크립트 본문. |

---

## 8. 트러블슈팅 및 가이드 (Quick Help)

1.  **배포 실패**: `status` 명령의 하단 이벤트를 확인하여 '리소스 부족'이나 '노드 선택 불가' 사유를 확인하십시오.
2.  **IP 미표시**: VM이 완전히 기동되기 전이거나 이미지가 복제 중(`PROGRESS` 확인)일 수 있습니다.
3.  **핀포인트 복구**: 일부 VM만 문제가 생겼을 때 `--target` 플래그를 사용하여 해당 인스턴스만 정밀 재배포 하십시오.

---
*Created for secure and reliable offline deployments by Technical Support Team.*
