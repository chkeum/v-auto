# 폐쇄망(Air-gapped) 환경 반입 및 설치 가이드

본 문서는 외부 인터넷이 차단된 Bastion 호스트 및 내부 망에 `v-auto` 도구를 안정적으로 반입하고 구축하기 위한 기술 절차를 안내합니다.

---

## 1. 외부망 준비 과정 (Off-site Preparation)

반입 전, 인터넷이 가능한 환경에서 실행에 필요한 모든 자산을 단일 번들로 준비합니다.

### 1-1. 의존성 패키지 다운로드
`v-auto` 디렉토리 내에 `packages` 폴더를 생성하고, 타겟 시스템에 맞는 바이너리 라이브러리를 준비합니다.

```bash
# 의존성 다운로드 (컴파일이 필요 없는 .whl 파일만 추출)
python3 -m pip download -d packages --only-binary=:all: PyYAML Jinja2
```

---

## 2. 폐쇄망 내 반입 및 구성 (In-site Setup)

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

---

## 3. 실행 및 검증 (Operation)

가상 환경의 파이썬 인터프리터를 사용하여 툴을 바로 실행합니다.

### 3-1. 배포 명령 실행
```bash
# 별도의 venv 활성화(source) 없이 바로 실행하는 것을 권장합니다.
./venv/bin/python3 vm_manager.py [project] [spec] deploy
```

---

## 4. 환경 최적화 팁

- **Alias 설정**: 매번 긴 경로를 입력하는 대신 단축어를 등록하십시오.
  `alias v-auto='/home/core/v-auto/venv/bin/python3 /home/core/v-auto/vm_manager.py'`
- **Log 확인**: `oc get dv,vmi -n [namespace]`를 통해 리소스 생성 및 이미지 임포트 과정을 모니터링하십시오.

---
*Created for secure and reliable offline deployments.*
