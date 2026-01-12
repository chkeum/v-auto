# VM 자동 배포 툴 사용자 가이드 (User Guide)

본 문서는 기술지원팀이 폐쇄망(Offline/Air-gapped) 환경에서 고객사(Vendor)의 VM을 배포하고 관리하기 위한 절차를 기술합니다.

---

## 1. 사전 준비 사항 (Prerequisites)

배포를 진행하기 전에 고객사로부터 다음 정보를 수집하고, 인프라 환경을 확인해야 합니다.

### 1-1. 고객사 제공 정보
*   **VM 이미지 파일**: `.qcow2` 형식의 운영체제 이미지 (예: Ubuntu, RHEL 등)
*   **VM 스펙**: 필요한 CPU Core 수, Memory 용량, Disk 크기.
*   **네트워크 정보**: 할당받을 IP 대역(CIDR), 게이트웨이 정보 (Secondary Network 사용 시).
*   **계정 정보**: VM 내부 접속용 Root/User 비밀번호 또는 SSH Public Key.

### 1-2. 인프라 환경 점검
*   **Internal Image Server**: 폐쇄망 환경이므로, 외부 인터넷 다운로드가 불가능합니다.
    *   준비된 `.qcow2` 이미지가 내부 HTTP 서버(예: `http://10.215.1.240/vm-images/...`)에 업로드되어 있어야 합니다.
    *   VM 배포 시 이 내부 URL을 사용합니다.
*   **Bastion Host**: `oc` CLI가 설치되어 있고, 타겟 OpenShift 클러스터에 `cluster-admin` 권한으로 로그인 가능한 상태여야 합니다.

---

## 2. 디렉토리 구조 및 관리

본 툴은 **디렉토리 기반**으로 업체를 관리합니다. `vendors/` 디렉토리 하위에 업체별 폴더를 생성하여 관리합니다.

### 2-1. 전체 구조
```text
v-auto/
├── manager.py                  # [실행] 배포 관리자 스크립트
├── deploy_vm.py                # [엔진] VM 배포 로직 (직접 실행 불필요)
├── templates/                  # [시스템] K8s 리소스 템플릿 (수정 불필요)
└── vendors/                    # [작업 공간] 업체별 데이터
    ├── samsung/                # [업체명]
    │   ├── config.yaml         # 업체 공통 설정 (Namespace, Network 등)
    │   └── vms/                # VM 개별 명세 폴더
    │       ├── web-01.yaml     # VM 스펙 정의서
    │       └── web-01-userdata.yaml # (선택) Cloud-Init 설정 파일
    └── lg/
        └── ...
```

---

### 2-2. 파일 구분 및 계층 구조의 이유 (Design Rationale)
이 구조는 **"공통 설정의 중앙 관리"**와 **"개별 리소스의 독립성"**을 위해 설계되었습니다.

1.  **`config.yaml` (Vendor Level)**:
    *   **역할**: 해당 업체의 *모든 VM이 공유하는 설정*을 정의합니다.
    *   **이유**: 업체가 50개의 VM을 운영한다고 가정해 봅시다. 네임스페이스(`namespace`)나 네트워크 설정(`nad_name`), 관리자 비밀번호가 변경될 때, 50개의 파일을 모두 수정하는 것은 비효율적이고 실수하기 쉽습니다. 이 파일 한 곳만 수정하면 해당 업체의 모든 VM에 변경 사항이 적용됩니다.
    *   **포함 정보**: Namespace, Network(NAD), 기본 계정 정보 등.

2.  **`vms/*.yaml` (VM Level)**:
    *   **역할**: 각 VM마다 *달라야 하는 스펙*만 정의합니다.
    *   **이유**: VM마다 CPU/Memory/Disk 용량이나 역할(DB, Web)은 서로 다릅니다. 여기에는 공통 설정을 제외한 순수한 스펙 정보만 남겨두어 파일을 간결하게 유지합니다.
    *   **포함 정보**: Hostname, CPU, Memory, Image URL 등.

---

## 3. 배포 설정 가이드 (Configuration)

기술지원팀은 `vendors/` 폴더 내에 파일을 작성해야 합니다.

### Step 1: 업체 디렉토리 생성
```bash
mkdir -p vendors/<업체명>/vms
# 예시
mkdir -p vendors/hyundai/vms
```

### Step 2: 업체 공통 설정 (`config.yaml`)
`vendors/<업체명>/config.yaml` 파일을 생성합니다.

```yaml
defaults:
  # 배포될 OpenShift Namespace (자동 생성됨)
  namespace: vm-hyundai
  
  # 네트워크 설정 (Multus)
  network:
    nad_name: hyundai-net             # NetworkAttachmentDefinition 이름
    # IPAM 설정 (Whereabouts 사용 시 CIDR 지정)
    ipam: '{ "type": "whereabouts", "range": "10.215.200.0/24" }'
  
  # 기본 계정 정보
  auth:
    username: hyundai-admin
    # 보안: 비밀번호는 파일에 평문으로 적지 않고 환경변수를 참조합니다.
    password: "env:HYUNDAI_PASSWORD"
```

### Step 3: VM 스펙 작성 (`vms/*.yaml`)
`vendors/<업체명>/vms/` 폴더 안에 VM별 YAML 파일을 생성합니다.

**기본형 (`database.yaml`)**:
```yaml
name: database-01
cpu: 4
memory: 8Gi
# 내부망 이미지 URL 필수
image: http://10.215.1.240/vm-images/rhel/rhel9.qcow2
storage_class: local-sc-test
```

**고급형 - Custom Cloud-Init 사용 (`web-server.yaml`)**:
복잡한 네트워크 설정이나 패키지 설치가 필요한 경우 사용합니다.
```yaml
name: web-server-01
cpu: 2
memory: 4Gi
image: http://10.215.1.240/vm-images/ubuntu/ubuntu-22.04.qcow2
# 별도로 작성한 Cloud-Init 파일 경로 지정
cloud_init: web-server-userdata.yaml
```

### Step 4: Cloud-Init 작성 (선택)
`cloud_init` 필드를 사용한 경우, 동일 폴더에 해당 파일을 작성합니다.
(`vendors/hyundai/vms/web-server-userdata.yaml`)

```yaml
#cloud-config
users:
  - name: admin-user
    passwd: $6$rounds... # 암호화된 비밀번호 권장
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
packages:
  - nginx
  - net-tools
runcmd:
  - systemctl start nginx
```

---

## 4. 배포 실행 (Execution)

### 4-1. 환경 변수 설정 (비밀번호 보안)
`config.yaml`에서 `env:VARIABLE_NAME`으로 지정한 변수에 실제 비밀번호를 입력합니다.
**이 작업은 터미널 세션마다 수행해야 하며, 기록엔 남지만 파일로 저장되지 않아 안전합니다.**

```bash
export HYUNDAI_PASSWORD='StrongPassword123!'
```

### 4-2. 배포 스크립트 실행
`manager.py`를 사용하여 특정 업체의 모든 VM을 일괄 배포합니다.

```bash
# 문법: python3 manager.py --vendor <업체디렉토리명>
python3 manager.py --vendor hyundai
```

**실행 시 일어나는 일:**
1.  `vm-hyundai` 네임스페이스가 없으면 생성합니다.
2.  `config.yaml`의 설정을 기반으로 네트워크(NAD)를 생성합니다.
3.  `vms/` 폴더 내의 모든 YAML 파일을 읽어 VM, Disk(PVC), Secret을 생성합니다.

---

## 5. 결과 확인 및 트러블슈팅

### 5-1. 배포 상태 확인
```bash
# VM 및 관련 리소스 조회
oc get vm,vmi,dv,pvc -n vm-hyundai

# VM이 Running 상태인지 확인
oc get vmi -n vm-hyundai
```

### 5-2. 접속 테스트 (Console)
OpenShift Web Console을 통해 접속하거나, `virtctl`을 사용합니다.
```bash
virtctl ssh <user>@<vm-name> -n vm-hyundai
```

### 5-3. 자주 발생하는 오류
1.  **SSL/TLS 인증서 오류**:
    *   증상: `SSLError ... certificate verify failed`
    *   해결: 본 툴은 내부적으로 SSL 검증을 무시하도록 패치되어 있으나, 지속 발생 시 `oc login` 상태를 점검하십시오.
2.  **Namespace Forbidden**:
    *   증상: `namespaces is forbidden`
    *   해결: 현재 로그인한 계정이 `cluster-admin` 권한이 있는지 확인하십시오 (`oc whoami`, `oc get clusterrolebinding`).
3.  **DataVolume Import 실패**:
    *   증상: DV가 `Pending` 또는 `ImportScheduled`에서 멈춤.
    *   해결: `StorageClass`의 `WaitForFirstConsumer` 설정 때문일 수 있습니다. VM이 스케줄링될 때까지 기다리거나, 스토리지 용량이 부족한지 확인하십시오 (`oc get pv`).

---
**문의**: 클라우드 기술지원팀 (support@example.com)
