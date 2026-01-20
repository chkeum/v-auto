# VM 배포 표준 운영 절차서 (Standard Operating Procedure)

> **문서 번호**: SOP-VM-01
> **담당 부서**: 기술지원팀 (Technical Support)
> **개요**: 고객의 요청에 따라 v-auto 도구를 사용하여 VM을 배포하고 인계하는 표준 절차를 정의한다.

---

## 1. 사전 준비 및 정보 수집 (Preparation)

작업 착수 전, 고객으로부터 다음 정보를 반드시 수령해야 합니다. (요청 양식 참조)

### 필수 확인 정보
1.  **프로젝트명 (Project)**: 고객사 또는 서비스 단위 (예: `opasnet`, `samsung`)
2.  **서비스 그룹명 (Spec)**: VM들의 논리적 그룹 (예: `web`, `db`, `backend`)
3.  **네트워크 구성 (Infrastructure)**:
    *   사용할 네트워크 대역 (CIDR) 및 게이트웨이
    *   VLAN 연동 여부 및 OpenShift NAD(NetworkAttachmentDefinition) 명칭
4.  **VM 제원 (Instance List)**:
    *   Hostname 및 고정 IP 주소
    *   OS 버전 (예: Ubuntu 22.04)
    *   CPU / Memory / Disk 규격

---

## 2. 작업 공간 생성 (Workspace Setup)

v-auto 작업 공간(`v-auto/projects/`)에 고객 전용 디렉토리를 생성합니다.

```bash
# 1. 툴 디렉토리로 이동
cd ~/v-auto

# 2. 프로젝트 디렉토리 생성 (이미 존재하면 생략)
# 형식: projects/[고객사명]
mkdir -p projects/opasnet
```

---

## 3. 스펙 파일 작성 (Specification Authoring)

고객 요구사항을 바탕으로 통합 스펙 파일(`YAML`)을 작성합니다.
파일 위치: `projects/[고객사명]/[서비스명].yaml` (예: `projects/opasnet/web.yaml`)

### 작성 예시 (Template)

아래 내용을 복사하여 상황에 맞게 수정하십시오.

```yaml
# ==========================================
# [1] 인프라 정의 (Infrastructure Definition)
# ==========================================
infrastructure:
  networks:
    default:                      # [중요] 인터페이스 별칭 (alias)
      nad: br-virt-net            # OpenShift NAD 이름 (고객사 환경에 맞게 수정)
      bridge: br-virt             # (참고용) 브리지 이름
      ipam:                       # IP 관리 정책
        type: whereabouts         # (고정/할당 방식)
        range: 10.215.100.0/24    # 네트워크 대역
        gateway: 10.215.100.1     # 게이트웨이 주소
      dns: [8.8.8.8]              # DNS 서버

  images:
    ubuntu-22.04:                 # 이미지 별칭
      url: "http://10.215.1.240/vm-images/ubuntu/ubuntu-22.04.qcow2"
      min_cpu: 2
      min_mem: 2Gi

# ==========================================
# [2] 공통 설정 (Common Configuration)
# ==========================================
common:
  image: "ubuntu-22.04"           # 위에서 정의한 이미지 별칭 사용
  network: default                # 위에서 정의한 네트워크 별칭 사용
  cpu: 4
  memory: 8Gi
  disk_size: 50Gi
  
  # 클라우드 초기화 (Cloud-Init)
  cloud_init:
    users:
      - name: admin               # 관리자 계정 생성
        passwd: "{{ user_password | hash_password }}" # 배포 시 입력받음
        groups: [sudo]
        shell: /bin/bash
    runcmd:
      - echo "Initial Setup Complete" > /root/setup.log

# ==========================================
# [3] 인스턴스 목록 (Instance List)
# ==========================================
instances:
  - name: web-01                  # 호스트네임
    ip: 10.215.100.101            # 고정 IP 할당
    
  - name: web-02
    ip: 10.215.100.102
    cpu: 8                        # (옵션) 특정 VM만 사양 변경 가능
```

---

## 4. 배포 및 검증 절차 (Deployment Process)

모든 작업은 `vman` 명령어를 통해 수행합니다.

### 📋 CLI 명령어 요약
| Action  | 설명 | 사용법 |
| :--- | :--- | :--- |
| **inspect** | 스펙 설정 및 IP 계산 결과 미리보기 (Dry-Run) | `./vman [PRJ] [SPEC] inspect` |
| **deploy** | 리소스 실제 생성 및 배포 (멱등성 보장) | `./vman [PRJ] [SPEC] deploy` |
| **status** | 배포된 VM 상태, IP, 디스크, 이벤트 조회 | `./vman [PRJ] [SPEC] status` |
| **delete** | 배포된 모든 리소스 삭제 | `./vman [PRJ] [SPEC] delete` |

---

### Step 1: 설정 검증 (Inspect)
작성한 스펙이 올바르게 해석되는지, 인프라 설정이 누락되지 않았는지 확인합니다.

```bash
# 사용법: ./vman [프로젝트] [스펙] inspect
./vman opasnet web inspect
```

**실행 예시**:
```text
══════════════════════════════════════════════════════════════════════
 🔍  CONFIGURATION INSPECTION REPORT | OPASNET/WEB
══════════════════════════════════════════════════════════════════════

 [1] PROJECT CONTEXT
 Namespace            : vm-opasnet
 Resources Defaults   : CPU=1, MEM=1Gi, Disk=10Gi
 --------------------------------------------------------------------

 [2] INFRASTRUCTURE CATALOG (Resolved)
 Networks             :
       pod-net         [POD   ] NAD: -               Bridge: -            Subnet: -
       default         [MULTUS] NAD: br-virt-net     Bridge: br-virt      Subnet: -
       storage         [MULTUS] NAD: br-storage-net  Bridge: br-storage   Subnet: -
 Images               :
       ubuntu-22.04    -> http://10.215.1.240/vm-images/ubuntu/ubuntu-22.04.qcow2
 --------------------------------------------------------------------

 [3] INSTANCE DEFINITIONS (Total: 2)

   [ INSTANCE: web-01 ]
       Specs           : Override (500mvCPU / 1Gi)
       IP Address      :
           - Auto/DHCP
       Interfaces      : default

   [ INSTANCE: web-02 ]
       Specs           : Default (1vCPU/1Gi)
       IP Address      :
           - Auto/DHCP
       Interfaces      : default, storage
 --------------------------------------------------------------------

 [4] CLOUD-INIT CONFIGURATION (User-Data Template)
      Users           :
        - core (Groups: [])
        - suser (Groups: [])
      RunCmd          : (4 commands)
        $ ['sh', '-c', "echo 'PasswordAuthentication yes' > /etc/ssh/sshd_config.d/99-force-pw.conf"]
        $ ['systemctl', 'restart', 'ssh']
        $ ['rm', '-f', '/etc/netplan/50-cloud-init.yaml']
        $ ['netplan', 'apply']

══════════════════════════════════════════════════════════════════════
```

### Step 2: 리소스 배포 (Deploy)
실제 OpenShift 리소스를 생성합니다.

```bash
# 사용법: ./vman [프로젝트] [스펙] deploy
./vman opasnet web deploy
```

**비밀번호 입력 정책**:
*   스펙(`web.yaml`)에 **Hardcoded Password**가 정의된 경우 (`chpasswd` 등), 비밀번호를 묻지 않고 즉시 배포가 진행됩니다.
*   변수(`{{ password }}`)가 사용된 경우에만 대화형 프롬프트가 나타납니다.
*   **현재 `opasnet/web` 스펙은 자동화 모드로 설정되어 있어 입력이 불필요합니다.**

**실행 예시 (Dry-Run)**:
`--dry-run` 옵션을 사용하면 실제 생성 전에 `VirtualMachine`, `DataVolume`, `Secret` 등 생성될 리소스의 상세 스펙을 미리 확인할 수 있습니다.

```text
 ─── [ VirtualMachine            | Name: web-02               ] ───
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: web-02
  namespace: vm-opasnet
  labels:
    v-auto/managed: 'true'
    v-auto/project: opasnet
    v-auto/spec: web
    v-auto/name: web-02
spec:
  running: true
  template:
    metadata:
      labels:
        kubevirt.io/vm: web-02
    spec:
      domain:
        devices:
          disks:
          - disk:
              bus: virtio
            name: root-disk
...
```
*   검증이 완료되면 `--yes` 옵션을 붙여 즉시 배포할 수 있습니다.

### Step 3: 상태 확인 (Status)
배포된 VM이 정상적으로 기동되었는지 확인합니다.

```bash
# 사용법: ./vman [프로젝트] [스펙] status
./vman opasnet web status
```

**실행 예시**:
```text
[ Detailed Status Diagnostic: opasnet/web ]
Target Namespace: vm-opasnet
====================================================================================================

1. Managed Virtual Machines (Health & Power)
----------------------------------------------------------------------------------------------------
KIND             NAME     STATUS    READY
VirtualMachine   web-01   Running   true
VirtualMachine   web-02   Running   true

2. Active Runtime & IP Addresses (VMI / Pod)
----------------------------------------------------------------------------------------------------
KIND                      NAME                           PHASE        ADDRESS            NODE
VirtualMachineInstance    web-01                         Running      -                  <none>
VirtualMachineInstance    web-02                         Running      -                  <none>
Pod                       virt-launcher-web-01-775xf     Running      192.168.5.112      worker1.chk-ocp.skt.local
Pod                       virt-launcher-web-02-4trnd     Running      192.168.4.55       worker2.chk-ocp.skt.local

3. Storage & Disk Provisioning (DataVolumes / PVC)
----------------------------------------------------------------------------------------------------
KIND         NAME               PHASE       PROGRESS
DataVolume   web-01-root-disk   Succeeded   100.0%
DataVolume   web-02-root-disk   Succeeded   100.0%

4. Network (NAD) & Config (Secret) Resources
----------------------------------------------------------------------------------------------------
KIND                          NAME                CREATED
NetworkAttachmentDefinition   br-storage-net      2026-01-19T19:16:29Z
NetworkAttachmentDefinition   br-virt-net         2026-01-19T19:16:26Z
Secret                        web-01-cloud-init   2026-01-19T19:16:26Z
====================================================================================================
```
*   **Check Point**:
    *   VirtualMachine 상태가 `Running` / `True` 인가?
    *   DataVolume(Disk)이 `Succeeded` (100%) 상태인가?
    *   Pod에 IP가 할당되었는가? (Multus IP는 VM 내부에서 확인 필요하지만, Pod IP 할당은 노드 스케줄링 성공을 의미함)

---

## 5. 변경 및 폐기 (Maintenance)

### VM 추가/변경
1.  스펙 파일(`web.yaml`)의 `instances` 리스트를 수정합니다.
2.  다시 `deploy` 명령을 실행합니다.
    *   **주의**: 기존에 잘 돌고 있는 VM은 건드리지 않고, **변경사항(비교)**만 자동으로 반영됩니다. (Idempotent)

### 특정 VM 재배포
특정 VM 하나만 문제가 있어 초기화해야 할 경우 `--target` 옵션을 사용합니다.
```bash
./vman opasnet web deploy --target web-02
```

### 전체 삭제 (Cleanup)
프로젝트 종료 시 자원을 회수합니다.

```bash
# 사용법: ./vman [프로젝트] [스펙] delete
./vman opasnet web delete
```

**실행 예시**:
```text
Gathering resources for deletion in namespace 'vm-opasnet'...

THE FOLLOWING RESOURCES WILL BE PERMANENTLY DELETED:

[ 1. Managed Resources (Selector: v-auto/project=opasnet,v-auto/spec=web) ]
KIND                          NAME                STATUS    PHASE       READY
VirtualMachine                web-01              Running     -         true
VirtualMachine                web-02              Running     -         true
DataVolume                    web-01-root-disk      -       Succeeded     -   
DataVolume                    web-02-root-disk      -       Succeeded     -   
PersistentVolumeClaim         web-01-root-disk      -       Bound         -   
PersistentVolumeClaim         web-02-root-disk      -       Bound         -   
Secret                        web-01-cloud-init     -         -           -   
Secret                        web-02-cloud-init     -         -           -   
NetworkAttachmentDefinition   br-storage-net        -         -           -   
NetworkAttachmentDefinition   br-virt-net           -         -           -   

Are you sure you want to proceed with deletion? [y/N]:
```
*   `y`를 입력하면 위 리소스가 모두 삭제됩니다. (VM이 Running 상태여도 강제 종료 후 삭제됨)

---

## 6. 문제 해결 (Troubleshooting)

**Case 1: "Valid networks resolving error" 발생**
*   **원인**: 스펙 파일의 `network: ...` 에 적은 이름이 `infrastructure/networks` 섹션에 정의되지 않았습니다.
*   **조치**: 오타를 확인하거나 infrastructure 정의를 추가하십시오.

**Case 2: "IP already in use" 에러**
*   **원인**: 할당하려는 고정 IP를 다른 VM이 이미 사용 중입니다.
*   **조치**: `status` 명령으로 사용 중인 IP를 확인하고, 다른 IP를 할당하십시오.

---
**Technical Support Team Confidential**
