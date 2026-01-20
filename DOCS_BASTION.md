# 폐쇄망(Air-gapped) 환경 반입 및 설치 가이드 (DOCS_BASTION)

본 문서는 외부 인터넷이 차단된 Bastion 호스트 및 내부 망에 `v-auto` 도구를 안정적으로 반입하고 구축하기 위한 기술 절차를 안내합니다.

---

## 1. 배포 번들 획득 (Getting the Package)

인터넷이 가능한 환경에서 최신 배포본(Bundle)을 다운로드하여 Bastion 서버로 반입합니다.

- **다운로드 경로**: `https://github.com/chkeum/v-auto/raw/main/releases/v-auto-packaged.tar.gz`
- **반입 방법**: USB 또는 망간연동 솔루션을 통해 내부 Bastion 서버의 임의 경로(예: `/home/core/`)로 파일을 이동합니다.

---

## 2. 폐쇄망 내 구성 (In-site Setup)

내부 망의 Bastion 서버에 번들을 반입한 후 설치를 진행합니다.

### 2-1. 번들 압축 해제
준비된 `v-auto-packaged.tar.gz` 파일을 원하는 경로(예: `/home/core/`)에 풀고 이동합니다.

```bash
tar -xvzf v-auto-packaged.tar.gz
cd v-auto
```

### 2-2. 격리된 실행 환경(venv) 구축
시스템 파이썬을 오염시키지 않고 독립적인 작동을 보장하기 위해 가상 환경을 생성하고 포함된 패키지를 설치합니다.

```bash
# 1. 가상 환경 생성
python3 -m venv venv

# 2. 오프라인 설치 (내부 packages 폴더 활용)
./venv/bin/python3 -m pip install --no-index --find-links=packages PyYAML Jinja2
```

## 3. 실행 및 검증 (Operation)

설치가 완료된 후의 **모든 운영 절차(검증, 배포, 조회, 삭제)**는 사용자 매뉴얼을 따릅니다.

👉 **[DOCS_USER.md](./DOCS_USER.md) 문서를 참조하십시오.**
  - `vman` 스크립트 사용법
  - 스펙 작성 및 검증 (`inspect`)
  - 배포 및 상태 확인 (`deploy`, `status`)

---
*Created for secure and reliable offline deployments.*
