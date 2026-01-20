# v-auto: OpenShift VM Delivery Tool (v1.0)

**v-auto**는 기술지원팀(Technical Support)이 고객의 요청에 따라 OpenShift Virtualization 기반의 VM을 신속하고 정확하게 배포하기 위해 사용하는 **자동화 도구**입니다.

복잡한 OpenShift 리소스(PVC, Service, Route, NetworkAttachmentDefinition 등)를 직접 생성하지 않고, **단일 YAML 명세(Spec)**만으로 표준 인프라를 구축할 수 있습니다.

---

## 📚 문서 가이드 (Documentation)

이 도구는 기술지원팀 엔지니어가 직접 운영합니다. 아래 문서를 순서대로 참고하십시오.

### 📘 [표준 운영 절차서 (SOP) - DOCS_USER.md](DOCS_USER.md)
**"고객으로부터 VM 생성 요청을 받았습니다. 어떻게 처리해야 하나요?"**
*   고객 요구사항 접수 및 정보 수집 양식
*   프로젝트 및 스펙 파일 작성 방법
*   `vman` 툴을 이용한 배포 및 검증 절차 (Step-by-Step)
*   **[필독]** 업무 수행 시 이 문서를 기준으로 작업을 진행하십시오.

### ⚙️ [시스템 아키텍처 및 템플릿 구조]
**"툴의 내부 동작 원리가 궁금합니다."**

#### 1. vman과 vm_manager.py
*   **vman**: 사용자 편의를 위한 쉘 스크립트 래퍼(Wrapper)입니다. 실행 인자를 정리하여 `vm_manager.py`로 전달합니다.
*   **vm_manager.py**: 툴의 핵심 엔진입니다.
    *   **Spec Parsing**: YAML 파일을 읽어 프로젝트 및 인프라 정보를 해석합니다.
    *   **Context Generation**: Jinja2 템플릿 엔진에 주입할 변수(Context)를 생성합니다. (IP 계산, 비밀번호 해싱 등)
    *   **Resource Rendering**: `infrastructure/templates/*.yaml` 파일을 렌더링하여 최종 OpenShift YAML을 생성합니다.
    *   **K8s Interaction**: `oc` CLI를 호출하여 리소스를 생성(`apply`), 조회(`get`), 삭제(`delete`) 합니다.

#### 2. 템플릿 시스템 (Infrastructure as Code)
모든 리소스는 `infrastructure/templates/` 디렉토리 내의 Jinja2 템플릿으로 정의됩니다.
이 파일을 수정하면 **모든 배포되는 VM의 표준 형상이 변경**됩니다.

*   `vm_template.yaml`: **VirtualMachine** 리소스 (CPU, Mem, Cloud-Init 연결)
*   `datavolume_template.yaml`: **DataVolume** 리소스 (디스크, PVC, StorageClass)
*   `secret_template.yaml`: **Secret** 리소스 (Cloud-Init User Data, Network Config)
*   `nad_template.yaml`: **NetworkAttachmentDefinition** 리소스 (Multus 브리지 연결)

> **주의**: 템플릿 수정은 시스템 전체에 영향을 미치므로 신중하게 수행해야 합니다. 문법 오류 시 모든 배포가 실패할 수 있습니다.

### 🏰 [폐쇄망 구축 가이드 - DOCS_BASTION.md](DOCS_BASTION.md)
**"인터넷이 차단된 고객사(Bastion) 환경에 툴을 설치해야 합니다."**
*   오프라인 번들(`tar.gz`) 반입 및 설치 절차
*   Python 가상 환경(venv) 구성 방법

---

## 🏗 디렉토리 구조
```text
v-auto/
├── vman                  # 🚀 실행 툴 (CLI Wrapper)
├── projects/             # [작업 공간] 고객별 프로젝트 관리
│   └── [고객사명]/
│       └── [서비스명].yaml # <--- 엔지니어가 작성할 통합 명세서 (Spec)
├── infrastructure/       # [시스템] 템플릿 및 리소스 정의
├── DOCS_USER.md          # 👈 표준 운영 절차서 (Main SOP)
└── vm_manager.py         # 핵심 로직 (Python)
```

---

*Developed by Core for Technical Support Excellence.*
