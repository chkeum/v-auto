# v-auto: OpenShift VM Deployment Automation (v2.0)

**v-auto**는 OpenShift Virtualization 환경을 위한 **Infrastructure as Code (IaC)** 자동화 도구입니다.  
복잡한 VM 설정을 추상화하여, 개발자는 **"스펙 정의(Spec)"**에만 집중하고 운영자는 **"표준 인프라(Infra)"**를 관리할 수 있도록 설계되었습니다.

---

## 📚 문서 가이드 (Documentation)

당신의 역할(Role)에 맞는 가이드를 선택하세요.

### 👩‍💻 [사용자 가이드 (DOCS_USER.md)](DOCS_USER.md)
**"저는 개발자입니다. VM을 빨리 띄워서 서비스를 올리고 싶어요."**
*   따라하기 쉬운 **5분 퀵스타트**
*   내 서버 정의하는 법 (`specs/*.yaml`)
*   배포, 상태 확인, 삭제 명령어

### 👷 [인프라 운영 가이드 (DOCS_INFRA.md)](DOCS_INFRA.md)
**"저는 플랫폼 관리자입니다. 네트워크와 스토리지 표준을 잡아야 해요."**
*   인프라 디렉토리 구조 (`infrastructure/`)
*   네트워크/이미지 카탈로그 정의법
*   보안 정책 및 템플릿 관리

---

## 🌟 v2.0 주요 변경 사항 (New!)

*   **📂 구조 분리**: `projects/`(사용자)와 `infrastructure/`(운영자) 폴더가 완벽히 분리되었습니다.
*   **📝 명시적 인스턴스**: 모호한 `replicas` 대신 `instances` 리스트로 IP를 명확히 관리합니다.
*   **🔒 보안 강화**: 비밀번호 자동 해싱 및 관리자 백도어 키 자동 주입 기능이 추가되었습니다.
*   **🤖 네트워크 자동화**: 게이트웨이, DNS 등 복잡한 설정이 자동 주입됩니다.

---

## 🏗 디렉토리 구조
```text
v-auto/
├── DOCS_USER.md          # 👈 개발자는 이것만 보세요!
├── DOCS_INFRA.md         # 👈 운영자는 이것을 보세요.
├── vm_manager.py         # 실행 툴 (건드리지 마세요)
├── projects/             # [사용자 영역] VM 스펙 정의
│   └── opasnet/
├── infrastructure/       # [운영자 영역] 네트워크/이미지 정의
└── ...
```

---
*Developed by Core for Technical Support Excellence.*
