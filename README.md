# v-auto: OpenShift VM Deployment Automation

`v-auto`는 OpenShift Virtualization 환경에서 가상 머신(VM)의 배포와 관리를 자동화하는 경량 CLI 도구입니다. 특히 외부 네트워크가 차단된 **폐쇄망(Air-gapped) 환경**에서도 모든 의존성을 포함하여 안정적으로 동작하도록 설계되었습니다.

---

## � Key Features

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

## 🚀 Quick Start

### 1. 프로젝트 설정
`projects/samsung/config.yaml`과 `projects/samsung/specs/web.yaml`을 성격에 맞게 작성합니다.

### 2. VM 배포
```bash
# 기본 실행
python3 vm_manager.py samsung web deploy

# 대수 지정 배포 (3대 배포)
python3 vm_manager.py samsung web deploy --replicas 3
```

### 3. VM 삭제 (지능형 라벨 기반)
```bash
# 해당 스펙으로 배포된 모든 리소스 일괄 삭제
python3 vm_manager.py samsung web delete
```

---

## 📖 Documentation

더 상세한 정보가 필요하시면 아래 문서를 참조해 주세요.

- **[설치 및 폐쇄망 반입 가이드](BASTION_TEST_GUIDE.md)**: 번들링부터 현장 설치까지의 절차.
- **[상세 설정 및 아키텍처 가이드](USER_GUIDE.md)**: YAML 작성법 및 라벨링 시스템 상세 설명.

---
*Developed by Core for Technical Support Excellence.*
