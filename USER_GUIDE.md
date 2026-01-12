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
- **`--target NAME`**: 특정 인스턴스(예: `web-02`)만 핀포인트로 배포/삭제/조회합니다. 이름의 숫자를 읽어 IP를 자동 계산합니다.
- **`--project` / `--spec`**: 위치 기반 인자 대신 명시적으로 지정할 때 사용합니다.

---

## 2. 계정 및 인증 설정 (Authentication)

`v-auto`는 보안을 위해 패스워드를 파일에 직접 저장하지 않고, 실행 시 안전하게 주입받는 방식을 취합니다.

### 2-1. 지능형 계정 감지 (Account Discovery)
- **동작**: `cloud_init` 내의 `passwd: {{ password }}` 또는 사용자를 정의한 섹션을 분석하여, 실행 시 적절한 입력 프롬프트를 자동으로 띄웁니다.
- **주입**: 입력받은 값은 `Secret` 리소스로 인코딩되어 저장되며, VM 기동 시 `cloud-init`을 통해 안전하게 주입됩니다.

### 2-2. YAML 정의 예시
```yaml
# spec.yaml
auth:
  username: admin  # 프롬프트에 표시될 기본 사용자명
cloud_init: |
  #cloud-config
  users:
    - name: tech-support
      passwd: {{ password }} # 실행 시 'Password for tech-support:' 프롬프트 생성
```

---

## 3. 네트워크 설계 (Network Architecture)

멀티 NIC 구성과 지능형 IPAM(IP Address Management)을 지원합니다.

### 3-1. 프로젝트 네트워크 카탈로그 (`config.yaml`)
하나의 프로젝트에서 사용할 수 있는 모든 네트워크 규격을 정의합니다.

```yaml
networks:
  default:
    bridge: br-ex            # OCP 노드의 실제 브리지 이름
    ipam:
      range: "10.10.10.0/24" # 자동 할당용 대역
      gateway: "10.10.10.1"
  mgmt-net:
    bridge: br-mgmt          # 관리용 폐쇄망 브리지
    # ipam이 없으면 DHCP 또는 외부 할당으로 동작
```

### 3-2. 고정 IP 자동 계산 로직
- **원리**: `range`가 정의된 네트워크를 사용할 때, 툴은 `IP = Network_Addr + 101 + index` 공식을 적용합니다.
- **결과**: `web-01`(.101), `web-02`(.102) ... 처럼 순차적으로 부여되어 IP 충돌을 원천 차단합니다.
- **동기화**: 계산된 IP는 K8s의 `NAD(NetworkAttachmentDefinition)`와 VM 내부(`cloud-init`)에 동시에 고정값으로 주입됩니다.

---

## 4. 스토리지 및 디스크 (Storage & Disk)

`DataVolume`을 통해 원본 이미지를 복제하고 VM의 영구 저장소(PVC)를 관리합니다.

### 4-1. 주요 설정 항목
- **`storage_class`**: Ceph-RBD 등 클러스터의 영구 저장소 규격을 지정합니다.
- **`disk_size`**: VM이 사용할 실제 디스크 공간입니다. 원본 이미지보다 커야 합니다.
- **`scratch PVC`**: 이미지 복제 시 CDI가 임시로 사용하는 공간입니다. 완료 후 자동 삭제되며, 실패 시 `v-auto status`에서 진행률과 함께 상태를 모니터링할 수 있습니다.

---

## 5. 고급 스케줄링 (Scheduling & Affinity)

VM이 특정 하드웨어나 위치(Rack)에 배치되도록 정교하게 제어합니다.

### 5-1. 다중 nodeSelector (Hard Constraint)
여러 라벨을 지정하여 **모든 조건이 일치**하는 노드에만 배치합니다.
```yaml
node_selector:
  zone: "core"
  hw-type: "high-mem"
```

### 5-2. Node Affinity (Complex Rules)
Kubernetes 표준 `affinity` 문법을 지원합니다. (Preferred/Required 모두 가능)
```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution: # 필수 조건
      nodeSelectorTerms:
      - matchExpressions:
        - key: "rack"
          operator: "In"
          values: ["rack-01"]
```

---

## 6. YAML 풀 사양 명세 (Full Spec Reference)

기술지원팀이 작성하는 스펙 파일(`spec.yaml`)의 모든 사용 가능 필드입니다.

| 필드명 | 설명 | 필수 여부 | 예시 |
| :--- | :--- | :--- | :--- |
| `name_prefix` | 생성될 VM의 이름 접두사 | **필수** | `web`, `db` |
| `replicas` | 기본 복제본 수 | 선택 (기본 1) | `3` |
| `cpu` / `memory` | 하드웨어 자원 사양 | **필수** | `2`, `4Gi` |
| `image_url` | 원본 이미지 경로 (HTTP/S) | **필수** | `http://.../img.qcow2` |
| `disk_size` | OS 디스크 용량 | **필수** | `40Gi` |
| `networks` | 사용할 네트워크 리스트 | 선택 | `['default']` |
| `node_selector` | 노드 라벨 선택기 (Dict) | 선택 | `{gpu: "enabled"}` |
| `affinity` | 고급 스케줄링 규칙 (Dict) | 선택 | `nodeAffinity: ...` |
| `cloud_init` | 부팅 시 자동 설정 스크립트 | 선택 | `#cloud-config ...` |

---

## 7. 트러블슈팅 케이스 (Total Checklist)

- **상태 확인**: `status` 명령 시 `ADDRESS`가 안 뜬다면 `DataVolume` 복제 상태(`PROGRESS`)를 확인하십시오.
- **이벤트 확인**: `Recent Events` 섹션의 **Warning** 메시지는 하드웨어 자원 부족이나 네트워크 브리지 미작동 사유를 즉시 알려줍니다.
- **삭제 후 잔재**: `delete` 명령은 `scratch` PVC 등 임시 자원도 패턴 기반으로 함께 정리합니다.

---
*Created for secure and reliable offline deployments by Technical Support Team.*
