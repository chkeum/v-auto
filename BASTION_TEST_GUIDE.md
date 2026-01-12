# 폐쇄망 Bastion 서버 테스트 가이드 (Air-gapped Environment)

본 문서는 외부 인터넷이 차단된 상용 Bastion 환경에서 VM 자동 배포 툴을 테스트하기 위한 준비 및 실행 절차를 안내합니다.

---

## 1. 사전 준비 (Off-site Preparation)

폐쇄망 반입 전, **인터넷이 가능한 환경**에서 모든 라이브러리를 `v-auto` 디렉토리 내에 미리 준비합니다.

### 1-1. Python 패키지 다운로드
`v-auto` 디렉토리 내부에 `packages` 폴더를 만들어 의존성 라이브러리를 다운로드합니다. 이 툴은 가벼운 구동을 위해 OCP SDK 대신 시스템 명령어를 직접 호출하므로, Python 패키지는 단 2가지만 필요합니다.

> [!NOTE]
> **왜 OCP 전용 라이브러리(openshift, kubernetes)는 안 받나요?**
> 우리 툴은 `oc` CLI 명령어를 내부적으로 사용하도록 설계되었습니다. 따라서 무거운 Python SDK를 설치하는 대신, Bastion에 이미 설치된 `oc` 도구를 활용합니다. 이 방식이 환경 변화에 가장 강하고 설치가 간편합니다.

```bash
# 1. 툴 저장소로 이동
cd v-auto

# 3. 의존성 패키지 다운로드 (바이너리 파일 강제)
# (--only-binary=:all: 옵션은 컴파일이 필요 없는 .whl 파일만 받도록 합니다)
python3 -m pip download -d packages --only-binary=:all: PyYAML Jinja2
```

> [!CAUTION]
> **`.tar.gz`와 `.whl`의 차이점 (중요)**
> - **`.whl` (Binary)**: 설치 준비가 끝난 파일입니다. 폐쇄망 서버에 컴파일러가 없어도 즉시 설치됩니다. (권장)
> - **`.tar.gz` (Source)**: 설치 시 서버에서 직접 빌드해야 하는 소스 파일입니다. Bastion 서버에 `gcc` 같은 빌드 도구가 없으면 설치에 실패할 수 있습니다.
> 
> 따라서 가급적 모든 패키지를 **`.whl` 확장자**로 준비해야 현장에서의 변수를 줄일 수 있습니다.

> [!TIP]
> **`-bash: pip: command not found` 오류가 발생하나요?**
> 일부 시스템에서는 `pip` 명령어가 바로 등록되어 있지 않을 수 있습니다. 이 경우 다음 방법 중 하나를 시도하십시오:
> 1. `python3 -m pip ...` (파이썬 모듈로 실행 - 권장 방식)
> 2. `pip3 ...` (대문자/숫자 확인)
> 3. `sudo apt install python3-pip` (OS에 pip가 설치되지 않은 경우)

### 1-2. 전체 패키징 및 Git 관리 (추천)
반입을 위해 전체를 압축하는 것도 좋지만, **`packages` 폴더 자체를 Git으로 관리**하면 소스 코드와 의존성 라이브러리를 항상 한 세트로 유지할 수 있어 더욱 편리합니다.

> [!TIP]
> **왜 압축 파일(`.tar.gz`) 대신 폴더를 Git으로 관리하나요?**
> Git은 바이너리(압축 파일)의 변경 사항을 추적하는 데 비효율적입니다. 반면 `packages/` 폴더 내의 `.whl` 파일들을 Git에 추가해두면, 클론(Clone)만으로 폐쇄망용 자산이 준비되며 형상 관리도 훨씬 깔끔합니다.

```bash
# 1. packages 폴더 내의 모든 '.whl' 파일을 Git 관리 대상에 등록 (Stage)
# (*.whl은 모든 패키지 설치 파일을 의미합니다)
git add packages/*.whl

# (선택) 새로 만든 bundle.sh나 수정된 코드도 함께 등록
git add bundle.sh BASTION_TEST_GUIDE.md vm_manager.py

# 2. 커밋 (이제 저장소에 라이브러리 파일이 영구히 저장됩니다)
git commit -m "Add offline dependencies and update guide"
```

> [!CAUTION]
> **`-bash: Changes not staged for commit` 메시지가 나오나요?**
> Git은 파일을 수정했다고 해서 바로 커밋(저장)할 수 없습니다. 반드시 **`git add <파일명>`** 명령어로 "이 파일을 저장할 목록에 올리겠다"고 먼저 말해줘야 합니다.
> - **Untracked files**: Git이 아직 존재조차 모르는 파일입니다. (`bundle.sh` 등)
> - **Modified**: 수정은 됐지만 저장 목록(Stage)엔 올라가지 않은 상태입니다.
> 
> **한 번에 해결하려면?**: `git add .` (현재 폴더의 모든 변경 사항을 목록에 담기)를 실행한 후 다시 커밋해 보세요.

### 1-3. 패키징 및 Git 업로드 자동화 (추천)
위의 압축 및 Git 업로드 과정을 한 번에 수행하는 `bundle.sh` 스크립트를 사용할 수 있습니다.

```bash
# 스크립트 실행 권한 부여 (최초 1회)
chmod +x bundle.sh

# 자동 번들링 및 Git 푸시 실행
# 실행 시 버전 태그를 인자로 줄 수 있습니다 (생략 시 오늘 날짜)
./bundle.sh v1.0.0
```

> [!NOTE]
> **`bundle.sh`가 하는 일:**
> 1. `packages/` 폴더 내 의존성 파일 확인.
> 2. `venv`, `.git` 등을 제외하고 `v-auto-packaged.tar.gz` 압축 생성.
> 3. `releases/` 폴더로 이동 및 Git 스테이징.
> 4. Git 커밋 및 원격 서버로 푸시.

> [!TIP]
> **Git LFS 활용 추천**
> 압축 파일의 용량이 크다면 `git lfs install` 후 `git lfs track "*.tar.gz"` 설정을 통해 바이너리 파일을 더 효율적으로 관리할 수 있습니다.

### 1-3. 반입물 목록 (Checklist)
USB 또는 기술 자산 반입 절차를 통해 다음 항목을 준비하십시오.
- [ ] `v-auto-packaged.tar.gz` (전체 소스 + 패키지 포함)
- [ ] 클러스터 접속 정보 (API URL, ID/PW)
- [ ] 테스트할 VM 이미지 (내부 이미지 서버 업로드용)

---

## 2. 폐쇄망 환경 구성 (In-site Setup)

Bastion 서버에서 내부 Git 서버로부터 파일을 다운로드하여 설치를 진행합니다.

### 2-1. 번들 다운로드 및 압축 해제
Git 전체를 클론하지 않고, 특정 압축 파일만 빠르게 내려받아 설치할 수 있습니다.

> [!NOTE]
> **어느 디렉토리에 압축을 구나요?**
> 우리 툴은 실행 파일 위치를 기준으로 모든 경로를 찾기 때문에 **어디에 압축을 풀어도 상관없습니다.** (예: `/home/core/`, `/opt/`, `/tmp/` 등)
> 다만, 다음 사항만 확인해 주세요:
> 1. **쓰기 권한**: 가상 환경(`venv`)을 만들고 설정을 저장해야 하므로 해당 계정이 파일을 쓸 수 있는 곳이어야 합니다.
> 2. **사용자 홈 권장**: 운영 체계 구분을 위해 `/home/<user>/` 이하에 두는 것이 가장 일반적이고 관리하기 좋습니다.

```bash
# 1. 내부 Git 서버에서 압축 파일 다운로드 (URL은 서버 환경에 맞게 수정)
# GitLab 예시: http://<git-server>/<user>/<repo>/-/raw/main/releases/v-auto-packaged.tar.gz
curl -L -O http://internal-git.local/tools/v-auto/-/raw/main/releases/v-auto-packaged.tar.gz

# 2. 압축 해제 및 이동
tar -xvzf v-auto-packaged.tar.gz
cd v-auto
```

### 2-2. 가상 환경 생성 및 로컬 패키지 설치
외부 네트워크 없이 내부에 포함된 `packages` 폴더를 사용하여 즉시 설치를 완료합니다.

> [!NOTE]
> **그냥 `python3`로 실행해도 잘 되는데, 왜 `venv`를 쓰나요?** (환경 격리)
> 1. **시스템 Python (`python3`)**: 서버 운영체제 전체가 사용하는 공용 공간입니다. 만약 다른 프로그램이 더 낮거나 높은 버전의 라이브러리를 요구한다면 우리가 만든 툴이 오작동할 수 있습니다.
> 2. **가상 환경 (`./venv/bin/python3`)**: 우리 툴만을 위한 **독립된 방**입니다. 서버의 다른 설정에 상관없이 우리가 반입한 정확한 버전의 라이브러리만 사용하므로, 어떤 고객사 서버에 가더라도 **100% 동일한 동작**을 보장합니다.
> 
> 폐쇄망 환경에서는 오류 발생 시 실시간으로 대처하기 어렵기 때문에, 가상 환경을 통해 **환경 변수(Side-effect)를 완벽히 차단**하는 것이 실무 표준입니다.

```bash
# 1. 가상 환경 생성 (설치 직후 1회만 수행)
python3 -m venv venv

# 2. 내부에 포함된 packages 폴더를 참조하여 설치
./venv/bin/pip install --no-index --find-links ./packages PyYAML Jinja2
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

### 4-1. 툴 실행 (가상 환경 활성화 없이 실행)
가상 환경 내의 Python을 직접 호출하여 실행할 수 있습니다. 이제 **위치 기반**과 **플래그(옵션) 기반** 형식을 모두 지원합니다.

```bash
# 방식 1: 직관적인 위치 기반 입력 (권장)
./venv/bin/python3 vm_manager.py samsung web deploy

# 방식 2: 명확한 플래그 기반 입력
./venv/bin/python3 vm_manager.py --vendor samsung --spec web deploy
```

> [!TIP]
> 더 간편하게 실행하려면 다음과 같이 별칭(alias)을 설정해두면 편리합니다:
> `alias v-auto='./venv/bin/python3 vm_manager.py'`
> 이후에는 `v-auto samsung web deploy`와 같이 짧게 실행 가능합니다.

### 4-2. VM 삭제 (Delete)
테스트가 끝난 VM 및 관련 자원(Disk, Secret 등)을 삭제합니다.

```bash
# 삭제 실행
./venv/bin/python3 vm_manager.py samsung web delete
```

### 4-3. 상태 확인 및 콘솔 접속
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
