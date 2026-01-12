# v-auto 기술 아키텍처 및 상세 설정 가이드

본 매뉴얼은 `v-auto`의 핵심 동작 원리와 설정 파일(YAML) 작성법, 그리고 라벨 기반의 리소스 수명 주기 관리(Lifecycle Management)에 대해 상세히 기술합니다.

---

## 1. 프로젝트 및 스펙 아키텍처

`v-auto`는 다수의 고객사나 환경을 격리하여 관리할 수 있도록 **Project**와 **Spec**의 계층 구조를 가집니다.

- **Project**: 네임스페이스, 공통 계정, 공통 네트워크 등 환경 전체의 정책을 결정합니다. (`projects/[name]/config.yaml`)
- **Spec**: 개별 VM의 CPU, 메모리, 이미지, Cloud-Init 등 구체적인 하드웨어/소프트웨어 정의를 담습니다. (`projects/[name]/specs/*.yaml`)

---

## 2. 설정 파일 작성법 (Configuration)

### 2-1. 프로젝트 공통 설정 (`config.yaml`)
모든 하위 Spec들이 상속받아 사용하는 글로벌 설정입니다.

```yaml
# 배포될 타겟 네임스페이스
namespace: vm-samsung-web

# 네트워크 인터페이스 리스트 (Multus NAD 활용)
interfaces:
  - nad_name: bond0-br-virt-net
    interface_name: eth1
    static_ip: 10.215.100.10/24
    ipam:
      type: static
      addresses:
        - address: 10.215.100.10/24
```

### 2-2. VM 개별 명세 (`specs/*.yaml`)
개 개별 VM의 고유 사양과 Cloud-Init 동작을 정의합니다.

```yaml
name_prefix: web   # 생성될 VM의 접두어
replicas: 2        # 배포할 수량
cpu: 2
memory: 4Gi
image_url: "http://10.215.1.240/vm-images/ubuntu-22.04.qcow2"
storage_class: local-sc-test

# Cloud-Init 설정 (Jinja2 템플릿 지원)
cloud_init: |
  #cloud-config
  users:
    - name: admin
      ssh_authorized_keys:
        - ssh-rsa AAAAB3N...
      sudo: ALL=(ALL) NOPASSWD:ALL
```

---

## 3. 라벨 기반 리소스 관리 시스템

`v-auto`는 배포되는 모든 리소스(VirtualMachine, DataVolume, Secret, NetworkAttachmentDefinition)에 다음과 같은 표준 라벨을 강제 주입합니다.

- `v-auto/managed`: "true"
- `v-auto/project`: [프로젝트명]
- `v-auto/spec`: [스펙명]
- `v-auto/name`: [VM명]

### 지능형 삭제 로직의 장점
- **안전성**: 설정 파일의 `replicas` 수치가 변경되거나 인자가 누락되어도, 클러스터를 조회하여 해당 라벨이 붙은 모든 자원을 정확히 찾아 지웁니다.
- **격리성**: 동일 네임스페이스 내에 다른 작업자가 생성한 자원을 건드리지 않고 오직 `v-auto`로 생성된 자원만 선별하여 정리합니다.

---

## 4. CLI 명령어 상세

| 기능 | 명령어 형태 | 설명 |
| :--- | :--- | :--- |
| **Deploy** | `... deploy [--replicas N]` | 지정된 프로젝트와 스펙으로 리소스를 생성합니다. |
| **Delete** | `... delete [--target NAME]` | 특정 VM 또는 해당 스펙의 전체 리소스를 라벨 기반으로 삭제합니다. |
| **List** | `... list` | 아직 구현 예정인 기능으로 현재는 `oc get`으로 대체 권장합니다. |

---
*Documentation for Technical Leaders.*
