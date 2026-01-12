# v-auto 기술 심층 가이드 (Deep Dive Technical Manual)

본 문서는 `v-auto`의 모든 작동 로직과 설정 케이스를 전수 조사하여 기술한 최종 기술 명세서입니다.

---

## 1. 리소스 수명 주기와 라벨링 시스템 (Lifecycle & Labeling)

`v-auto`는 오직 **라벨(Label)**을 기준으로 리소스를 관리합니다. 이는 이름 충돌이나 수동 삭제의 복잡함을 해결하기 위함입니다.

### 1-1. 주입되는 표준 라벨
모든 리소스(VM, DV, Secret, NAD)에는 다음 4가지 라벨이 강제 주입됩니다.
- `v-auto/managed`: `true` (본 도구에 의해 관리됨을 표시)
- `v-auto/project`: `[프로젝트명]` (예: `samsung`)
- `v-auto/spec`: `[스펙명]` (예: `web`)
- `v-auto/name`: `[VM 개별 이름]` (예: `web-01`)

### 1-2. 지능형 삭제 로직 (Delete Logic)
`delete` 명령 실행 시, 툴은 설정 파일의 `replicas` 값을 보지 않습니다. 대신 쿠버네티스 API에 다음과 같이 요청합니다.
- **전체 삭제**: `oc delete <resources> -l v-auto/project=samsung,v-auto/spec=web`
- **특정 삭제**: `oc delete <resources> -l v-auto/project=samsung,v-auto/spec=web,v-auto/name=web-01`
> **Case**: 만약 사용자가 `web.yaml`에서 대수를 5개에서 1개로 줄였더라도, 이전 배포된 5개의 자원을 모두 찾아내어 안전하게 삭제합니다.

---

## 2. 네트워크 구성 심층 분석 (Networking Case Study)

`v-auto`는 두 가지 네트워크 할당 방식을 지원합니다.

### Case A: 자동 할당 (DHCP / Whereabouts)
인프라 수준에서 IP를 관리하는 방식입니다.

**설정 예시 (`config.yaml`)**:
```yaml
interfaces:
  - nad_name: pod-net-dhcp
    # ipam 설정을 넣지 않거나, 타입을 지정하지 않으면 인프라 설정을 따름
```
- **작동**: `oc apply` 시 NAD가 생성되며, VM이 부팅될 때 인프라의 DHCP 서버나 `whereabouts` IPAM으로부터 IP를 받아옵니다.
- **Cloud-Init (가이드)**: VM 내부에서는 `dhcp4: true`로 설정해야 합니다.

### Case B: 지능형 고정 IP 할당 (v-auto Static Logic)
폐쇄망에서 IP 충돌을 방지하기 위해 툴이 직접 IP를 계산하여 주입하는 방식입니다.

**설정 예시 (`config.yaml`)**:
```yaml
interfaces:
  - nad_name: static-net
    ipam:
      range: "10.210.1.0/24"  # 툴이 이 대역에서 IP를 자동 계산함
      gateway: "10.210.1.1"
```
- **작동 (Step-by-Step)**:
    1.  **계산**: `replica-01`은 `.101`, `replica-02`는 `.102` 형식으로 IP를 계산합니다.
    2.  **NAD 변환**: `whereabouts` 설정을 `static` IPAM 설정으로 강제 변환하여 NAD를 생성합니다. (`addresses: ["10.210.1.101/24"]`)
    3.  **Cloud-Init 주입**: 계산된 IP 정보를 Cloud-Init의 `write_files` 또는 `netplan` 설정에 자동으로 변동 주입합니다.
- **Case**: 네트워크 설정 없이 `ipam.range`만 주면, 툴이 알아서 NAD와 VM 내부 설정을 일치시켜 줍니다.

---

## 3. 템플릿 렌더링 로직

`templates/` 디렉토리의 YAML들은 단순히 고정된 파일이 아니라 **Jinja2 엔진**에 의해 처리됩니다.

### 3-1. 변수 우선순위 (Variable Precedence)
1.  **CLI 인자**: `--replicas` 등 명령 실행 시 직접 주입한 값 (최우선)
2.  **VM Spec (`specs/*.yaml`)**: 개별 VM 정의 파일.
3.  **Project Config (`config.yaml`)**: 프로젝트 공통 설정. (최하위)

### 3-2. Cloud-Init 커스터마이징
`secret_template.yaml`은 `cloud_init_content` 변수가 있을 때만 데이터를 생성합니다. 만약 Spec YAML에 `cloud_init:` 섹션이 없다면 Secret은 빈 상태로 생성될 수 있으므로 주의하십시오.

---

## 4. 트러블슈팅 매트릭스 (Total Case)

| 상황 | 원인 및 해결 방법 |
| :--- | :--- |
| **VM 생성 중 멈춤** | `oc get dv -n [ns]`를 확인하십시오. 이미지 크기가 크면 `Importing` 과정이 길어질 수 있습니다. |
| **네트워크 미연결** | `oc get nad -n [ns]`를 확인하여 주입된 IP 정보와 VM 내부의 `ip a` 결과가 일치하는지 확인하십시오. |
| **삭제 시 자원 남음** | `v-auto` 버전 2.0 미만으로 생성된 자원(라벨 없음)일 수 있습니다. 수동 삭제(`oc delete`) 후 다시 배포하십시오. |

---
*This guide is the definitive source of truth for v-auto logic.*
