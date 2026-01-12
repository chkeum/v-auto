# v-auto 통합 기술 마스터 가이드 (Definitive Master Guide)

`v-auto`는 OpenShift Virtualization 환경에서 가상 머신(VM) 및 관련 자원(Disk, Network, Secret) 배포를 자동화하는 기술지원팀 전용 마스터 도구입니다. 본 문서는 도구의 사용법부터 YAML 설계 원칙까지 모든 내용을 담고 있습니다.

---

## 1. CLI 명령어 및 파라미터 (CLI Reference)

모든 명령은 `python3 vm_manager.py [PROJECT] [SPEC] [ACTION]` 형식을 따릅니다.

### 1-1. 핵심 액션 (Core Actions)
- **`deploy`**: 설계도(YAML)를 기반으로 인프라를 생성합니다. (이미 존재 시 `[SKIPPED]`)
- **`delete`**: 관련 자원을 안전하게 일괄 삭제합니다. (라벨 기반 정밀 삭제)
- **`status`**: 배포 현황, IP 주소, 디스크 복제율, 최근 **Warning 이벤트**를 통합 진단합니다.

### 1-2. 주요 플래그 (Primary Flags)
- **`--replicas N`**: YAML 설정을 무시하고 일시적으로 N대의 복제본을 배포합니다.
- **`--target NAME`**: 특정 인스턴스(예: `web-02`)만 핀포인트로 배포/삭제/조회합니다. 이름의 번호를 읽어 IP를 자동 계산합니다.
- **`--project` / `--spec`**: 위치 기반 인자 대신 명시적으로 지정할 때 사용합니다.

---

## 2. YAML 설계 가이드 (Configuration Deep Dive)

기술지원팀이 가장 중요하게 관리해야 하는 '설계도' 작성법입니다. **프로젝트 설정(`config.yaml`)**과 **개별 스펙(`spec.yaml`)**의 조합으로 완성됩니다.

### 2-1. 설정 상속 및 우선순위 (Inheritance Logic)
- **Level 1 (Project Config)**: 프로젝트 전체에 공통 적용되는 기본값 (Namespace, StorageClass, Network 목록).
- **Level 2 (Spec YAML)**: 개별 VM의 하드웨어 사양 및 소프트웨어 설정. 프로젝트 설정을 덮어쓸 수 있습니다.
- **Level 3 (CLI Flags)**: 실행 시점에 인자로 받는 값 (Replicas 등). 최종 우선순위를 가집니다.

### 2-2. [Project] config.yaml 작성법
프로젝트 루트(`projects/[name]/config.yaml`)에 위치하며, 하부 모든 스펙이 공유하는 자원을 정의합니다.

```yaml
namespace: samsung-web              # VM이 배포될 K8s 네임스페이스
storage_class: ocs-storagecluster   # 기본 스토리지 클래스 (Ceph-RBD 등)

networks:                           # 사용 가능한 네트워크 카탈로그
  default:                          # 기본 네트워크 이름
    bridge: br-ex                   # 실제 OCP 노드의 브리지명
    ipam:                           # IP 관리 (선택 사항)
      range: "10.10.10.0/24"        # 지정 시 툴이 .101부터 자동 할당
      gateway: "10.10.10.1"
  mgmt-net:                         # 관리용 추가 네트워크
    bridge: br-mgmt
    # ipam이 없으면 DHCP/External 할당으로 동작
```

### 2-3. [Spec] spec.yaml 작성법
개별 VM의 특성을 정의합니다. (`projects/[name]/specs/[service].yaml`)

```yaml
name_prefix: web                    # 생성될 VM 이름의 시작점 (예: web-01)
replicas: 2                         # 기본 복제본 수
cpu: 2                              # 코어 수
memory: 4Gi                         # 메모리 크기
image_url: "http://.../rhel9.qcow2" # 원본 이미지 경로 (HTTP/S)
disk_size: 40Gi                     # OS 디스크 용량

networks:                           # 사용할 네트워크 선택 (카탈로그 이름)
  - default                         # 첫 번째 NIC (eth0)
  - mgmt-net                        # 두 번째 NIC (eth1)

node_selector:                      # 특정 노드 그룹에 배치할 때
  region: "seoul"

cloud_init: |                       # 부팅 시 자동 설정 스크립트
  #cloud-config
  ssh_pwauth: True
  users:
    - name: admin
      passwd: {{ password }}        # 실행 시 입력받은 비밀번호 주입
```

---

## 3. 실무 배포 시나리오 (Operational Scenarios)

### Case 1. 웹 서버 클러스터 (Static IP 자동 할당)
- **요구사항**: 3대의 웹 서버를 `10.10.10.101~103` 주소로 배포.
- **방법**: `config.yaml`에 `ipam.range` 정의 후 `deploy` 시 `--replicas 3` 실행.

### Case 2. 특정 인스턴스 핀포인트 복구 (Pinpoint Recovery)
- **상황**: `web-02`만 네트워크 설정 전송 실패 등으로 재배포가 필요한 경우.
- **방법**: 
  ```bash
  python3 vm_manager.py samsung web deploy --target web-02
  ```
- **효과**: 다른 정상 VM은 건드리지 않고 `web-02`만 다시 생성하며 IP(.102)도 그대로 유지.

### Case 3. 고급 스케줄링 (Affinity)
- **요구사항**: 가급적 `SSD` 노드에 배치하되, 반드시 특정 랙에는 배치하지 않음.
- **설정**: Spec YAML에 `affinity` 블록 정의 (표준 K8s Affinity 문법 지원).

---

## 4. 트러블슈팅 및 관리 (Troubleshooting)

1.  **[SKIPPED] 메시지**: 동일 설정의 자원이 이미 있음을 의미합니다. 변경 사항을 강제 반영하려면 `delete` 후 `deploy` 하십시오.
2.  **IP 할당 확인**: `status` 명령을 실행하면 `ADDRESS` 열에 실제 할당된 IP가 바로 표시됩니다.
3.  **이벤트 모니터링**: `status` 하단의 `Recent Events`는 하드웨어 오류나 이미지 로딩 실패 사유를 **Warning** 등급 위주로 친절하게 보여줍니다.

---
*본 문서는 기술지원팀의 피드백을 반영하여 지속적으로 업데이트됩니다.*
