# v-auto 통합 기술 마스터 가이드 (The Definitive Guide)

`v-auto`는 OpenShift Virtualization 환경에서 가상 머신(VM) 배포를 자동화하는 기업용 CLI 도구입니다. 본 문서는 도구의 모든 기능과 내부 로직을 전수 공개하여, 초보자도 전문가 수준으로 도구를 활용할 수 있도록 돕습니다.

---

## 1. CLI 명령어 및 파라미터 전수 명세

`vm_manager.py`는 위치 기반 인자(Positional)와 플래그 기반 인자(Flag)를 지능적으로 조합하여 사용합니다.

### 1-1. 기본 명령 체계
```bash
python3 vm_manager.py [PROJECT] [SPEC] [ACTION] [OPTIONS]
```

### 1-2. 핵심 액션 (Actions)
- **`deploy`**: 리소스를 생성합니다. (VM, DataVolume, Secret, NAD)
- **`delete`**: 리소스를 삭제합니다. (라벨 및 이름 패턴 기반 지능형 삭제)
- **`status`**: 배포된 모든 리소스의 요약 현황부터 구동 상태, **IP 주소**, 디스크 복제 진행률, 최근 **이벤트**까지 전수 진단합니다.

### 1-3. 주요 스위치 (Flags)
- **`--replicas N`**: YAML에 정의된 `replicas` 수치를 무시하고 N대만큼 배포합니다.
- **`--target NAME`**: (`delete` / `status` 시) 특정 이름의 VM만 핀포인트로 삭제하거나 상태를 조회할 때 사용합니다.
- **`--project` / `--spec`**: 위치 인자 대신 명시적으로 프로젝트와 스펙을 지정할 때 사용합니다.

---

## 2. 배포 과정 및 실행 결과 해설

수행 시 화면에 출력되는 메시지들은 리소스의 현재 상태를 즉각적으로 보여줍니다.

### 2-1. 수행 결과 플래그 의미
| 플래그 | 의미 | 조치 방법 |
| :--- | :--- | :--- |
| **`[SUCCESS]`** | 리소스가 클러스터에 성공적으로 반영됨 | 다음 단계를 진행하거나 `oc get`으로 상태 확인 |
| **`[SKIPPED]`** | 동일한 이름과 설정의 리소스가 이미 존재함 | 기존 자원을 재사용하므로 별도 조치 불필요 |
| **`[FAILED]`** | 권한 문제나 설정 오류로 생성 실패 | 에러 메시지를 확인하여 YAML 오타나 권한 확인 |
| **`[DELETED]`** | 해당 리소스가 원격지에서 성공적으로 제거됨 | - |

---

## 3. 네트워크 할당 로직 (Deep Dive)

`v-auto`는 네트워크 설정 방식에 따라 IP를 계산하거나 인프라에 위임합니다.

### 3-1. 고정 IP 자동 계산 수식
`config.yaml`에 `ipam.range`가 정의되어 있으면 툴은 다음 로직을 적용합니다:
- **계산식**: `IP = Network_Address + 101 + index`
- **결과**: `replica-01` -> `.101`, `replica-02` -> `.102` ...
- **주입**: 계산된 값은 NAD의 `static` 주소와 Cloud-Init의 `{{ static_ip }}` 자리에 동시 주입되어 동기화를 보장합니다.

### 3-2. 외부/인프라 할당 (DHCP)
`ipam` 섹션이 없으면 `pod` 네트워크나 인프라의 DHCP 서버를 사용합니다. 이 경우 툴은 IP를 고정하지 않고 부팅 시 동적으로 받도록 둡니다.

---

## 4. 리소스 수명 주기 관리 (Labels)

모든 자원은 다음 라벨을 가지고 있으며, `delete` 명령은 이 라벨들을 셀렉터로 활용합니다.
- `v-auto/managed`: `true`
- `v-auto/project`: [Project Name]
- `v-auto/spec`: [Spec Name]
- `v-auto/name`: [Instance Name]

---

## 5. 고급 스케줄링 및 배치 제어 (Scheduling & Affinity)

운영 환경의 복잡한 요구사항에 맞춰 VM이 기동될 노드를 정밀하게 제어할 수 있습니다.

### 5-1. 다중 nodeSelector (Hard Constraint)
여러 개의 라벨을 지정하여 **모든 조건이 일치하는 노드**에만 VM을 배치합니다.
```yaml
node_selector:
  zone: "core"
  hw-type: "high-mem"
```

### 5-2. Node Affinity (Soft/Hard Constraint)
Kubernetes의 표준 `affinity` 문법을 그대로 사용하여 더욱 복잡한 배치 규칙을 적용할 수 있습니다. 툴은 내부적으로 이 설정을 JSON으로 변환하여 안전하게 주입합니다.
```yaml
affinity:
  nodeAffinity:
    preferredDuringSchedulingIgnoredDuringExecution: # 가급적 이 노드에 배치
    - weight: 1
      preference:
        matchExpressions:
        - key: "disktype"
          operator: "In"
          values: ["ssd"]
```

---

## 6. 트러블슈팅 케이스 (Total Checklist)

1.  **"Resource already exists"**: `deploy` 시 `[SKIPPED]`가 뜨는 것은 정상입니다. 강제 재배포가 필요하면 먼저 `delete`를 수행하십시오.
2.  **VM 이미지 로딩(Importing)**: 배포 직후 VM이 `Starting` 상태가 아닌 것은 `DataVolume`이 이미지를 복제 중이기 때문입니다. `status` 명령으로 `PROGRESS` 필드를 확인하십시오.
3.  **권한 오류**: `oc login`이 되어 있는지, 그리고 해당 네임스페이스에 대한 쓰기 권한이나 `cluster-admin` 권한이 있는지 확인하십시오.

## 6. 버전 및 배포본 확인 (Version Check)

`v-auto` 패키지(tar.gz) 내부에는 항당 해당 시점의 버전 정보가 담긴 `VERSION` 파일이 포함되어 있습니다.
- **확인 방법**:
  ```bash
  cat VERSION  # 예: v1.1.0 또는 v20260112
  ```
- **생성 시점**: `git_sync.sh` 또는 `bundle.sh` 실행 시 사용자가 지정하거나 날짜 기반으로 자동 생성됩니다.

---
*Created for secure and reliable offline deployments.*
