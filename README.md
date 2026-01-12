# v-auto: OpenShift VM Deployment Automation

`v-auto`는 OpenShift Virtualization 환경에서 가상 머신(VM)의 배포와 관리를 자동화하는 경량 CLI 도구입니다. 특히 외부 네트워크가 차단된 **폐쇄망(Air-gapped) 환경**에서도 모든 의존성을 포함하여 안정적으로 동작하도록 설계되었습니다.

---

## 🌟 Key Features

- **Project-based Management**: 프로젝트와 사양(Spec) 기반의 계층적 구조로 수많은 VM을 체계적으로 관리합니다.
- **Offline Bundle Generation**: 폐쇄망 반입을 위해 모든 Python 라이브러리와 바이너리를 포함한 단일 압축 번들을 제작합니다.
- **Label-based Lifecycle**: 쿠버네티스 라벨을 활용하여 배포된 VM과 관련 리소스(Disk, Network, Secret)를 정확하게 추적하고 원클릭으로 정리합니다.
- **Flexible CLI Arguments**: 위치 기반 인자와 플래그형 인자를 모두 지원하여 직관적인 사용자 경험을 제공합니다.
- **Infrastructure as Code**: YAML 기반 설정을 통해 VM의 CPU, Memory, Disk, Network, Cloud-Init을 명세화합니다.

---

## 🏗 Directory Structure

```text
v-auto/
├── vm_manager.py        # 핵심 실행 스크립트
├── projects/            # 프로젝트별 설정 공간
│   └── [project_name]/
│       ├── config.yaml  # 프로젝트 공통 설정 (Namespace, Auth 등)
│       └── specs/       # VM 사양 정의서 (.yaml)
├── templates/           # K8s 리소스 (VM, DV, NAD 등) Jinja2 템플릿
└── packages/            # 오프라인용 Python 의존성 (.whl)
```

---

## 📖 Documentation & Guides

도구를 처음 사용하신다면 아래 순서대로 읽어보시는 것을 권장합니다:

1.  **[기술 마스터 매뉴얼 (USER_GUIDE.md)](USER_GUIDE.md)**: **(필독)** YAML 작성법, CLI 옵션 명세, 실무 예제 및 기술 로직이 총망라된 통합 가이드.
2.  **[폐쇄망 반입 및 설치 가이드 (BASTION_TEST_GUIDE.md)](BASTION_TEST_GUIDE.md)**: 번들링부터 현장 설치까지의 절차.

---

## 🚀 5분 완성 퀵스타트

### 1단계: 프로젝트 준비
```bash
# 기본 제공되는 samsung 프로젝트 예시 확인
ls projects/samsung/specs/web.yaml
```

### 2단계: VM 배포 (Review 포함)
```bash
# 툴이 설정을 검토하고 대상을 보여줍니다. (y/n 확인 절차 포함)
python3 vm_manager.py samsung web deploy
```

### 3단계: 상태 확인 및 삭제
```bash
# 배포된 VM 리스트 및 상태 확인 (IP, 이벤트 정보 포함)
python3 vm_manager.py samsung web status

# 전체 리소스 안전하게 정리
python3 vm_manager.py samsung web delete
```

---
*Developed by Core for Technical Support Excellence.*
