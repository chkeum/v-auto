# 폐쇄망 Bastion 서버 테스트 가이드 (Air-gapped Environment)

본 문서는 외부 인터넷이 차단된 상용 Bastion 환경에서 VM 자동 배포 툴을 테스트하기 위한 준비 및 실행 절차를 안내합니다.

---

## 1. 사전 준비 (Off-site Preparation)

폐쇄망 반입 전, **인터넷이 가능한 환경**에서 모든 라이브러리를 `v-auto` 디렉토리 내에 미리 준비합니다.

### 1-1. Python 패키지 다운로드
`v-auto` 디렉토리 내부에 `packages` 폴더를 만들어 의존성 라이브러리를 다운로드합니다.
```bash
# 1. 툴 저장소로 이동
cd v-auto

# 2. 내부 패키지 디렉토리 생성
mkdir -p packages

# 3. 의존성 패키지 다운로드 (PyYAML, Jinja2 및 하위 의존성)
pip download -d packages PyYAML Jinja2
```

### 1-2. 전체 패키징
이제 `packages`를 포함한 전체 디렉토리를 하나로 압축합니다. 이때 **로컬 가상 환경(`venv`)이나 불필요한 파일은 제외**하여 용량을 줄이고 환경 간 충돌을 방지합니다.

> [!IMPORTANT]
> `venv` 폴더는 생성한 머신의 OS와 Python 버전에 종속적이므로, 함께 압축해서 반입하지 않고 현장(Bastion)에서 새로 생성하는 것이 원칙입니다.

```bash
cd ..
# venv, __pycache__, .git 등 불필요한 항목 제외하고 압축
tar --exclude='v-auto/venv' \
    --exclude='v-auto/.venv' \
    --exclude='*/__pycache__' \
    --exclude='v-auto/.git' \
    -cvzf v-auto-packaged.tar.gz v-auto/
```

### 1-3. 반입물 목록 (Checklist)
USB 또는 기술 자산 반입 절차를 통해 다음 항목을 준비하십시오.
- [ ] `v-auto-packaged.tar.gz` (전체 소스 + 패키지 포함)
- [ ] 클러스터 접속 정보 (API URL, ID/PW)
- [ ] 테스트할 VM 이미지 (내부 이미지 서버 업로드용)

---

## 2. 폐쇄망 환경 구성 (In-site Setup)

Bastion 서버에 접속하여 압축을 풀고 즉시 설치합니다.

### 2-1. 압축 해제 및 이동
```bash
tar -xvzf v-auto-packaged.tar.gz
cd v-auto
```

### 2-2. 가상 환경 생성 및 로컬 패키지 설치
외부 네트워크 없이 내부에 포함된 `packages` 폴더를 사용하여 즉시 설치를 완료합니다.
```bash
# 1. 가상 환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate

# 2. 내부에 포함된 packages 폴더를 참조하여 설치
pip install --no-index --find-links ./packages PyYAML Jinja2
```

---

## 3. 인프라 사전 점검

### 3-1. CLI 도구 및 권한
- `oc`, `virtctl` 도구 설치 여부 확인
- `oc login` 후 `cluster-admin` 권한 확인

### 3-2. 내부 이미지 서버 URL 확인
폐쇄망용 이미지 주소를 설정합니다.
- `projects/<vendor>/specs/*.yaml` 내의 `image` 필드를 내부 URL로 수정하십시오.

---

## 4. 테스트 실행 및 검증

### 4-1. 툴 실행
```bash
python3 vm_manager.py deploy --vendor samsung --spec web
```

### 4-2. 상태 확인 및 콘솔 접속
```bash
oc get vmi -n <namespace>
virtctl ssh <user>@<vm-name> -n <namespace>
```

---

## 5. 폐쇄망 주요 트러블슈팅

| 현상 | 원인 및 해결 방법 |
| :--- | :--- |
| `pip install` 실패 | `packages` 폴더 내에 모든 의존성이 포함되었는지 확인하십시오. (패키징 시 `pip download` 결과 확인 필수) |
| `Image Pull Error` | 내부 이미지 서버 주소가 Bastion 또는 물리 노드에서 접근 가능한지 확인하십시오. |
| `Permission Denied` | 반입된 파일의 실행 권한을 확인하십시오 (`chmod +x vm_manager.py`). |
