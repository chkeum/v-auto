# Git을 이용한 소스 코드 관리 및 배포 가이드

이 가이드는 현재 배포 서버에 있는 코드를 어떻게 안전하게Git으로 관리하고, 내 PC와 연동하여 효율적으로 작업할 수 있는지 단계별로 설명합니다.

---

## 1. 기본 개념 이해하기

우리는 총 3개의 지점을 연결할 것입니다:
1.  **배포 서버 (Bastion)**: 현재 코드가 있고, 실제 VM 배포가 일어나는 곳 (`vm_manager.py`가 실행되는 곳)
2.  **Git 서버 (GitHub/GitLab)**: 소스 코드의 "원본"과 "이력"이 저장되는 구름 위의 금고
3.  **내 PC**: 코드를 편리하게 수정하고 개발하는 작업실

---

## 2. [1단계] 배포 서버의 소스를 Git에 처음 저장하기

지금 서버에 있는 파일들을 Git의 관리 대상으로 등록하는 과정입니다.

```bash
# 1. 작업 디렉토리로 이동
cd /home/core/v-auto

# 2. Git 저장소 초기화 (Git 관리 시작)
git init

# 3. 관리 대상에서 제외할 파일 설정 (gitignore)
# 가상환경, 로그, 임시파일 등은 저장하지 않습니다.
cat <<EOF > .gitignore
__pycache__/
*.log
.tmp/
.vscode/
EOF

# 4. 현재 파일들을 장바구니에 담기
git add .

# 5. 첫 번째 기록 남기기 (Commit)
git commit -m "Initial commit: VM Management System with Samsung & Example projects"
```

---

## 3. [2단계] 외부 Git 서버(금고)에 연결하기

이제 GitHub나 GitLab에 프로젝트를 생성하고 서버와 연결해야 합니다.

1.  **GitHub/GitLab 접속**: 새 프로젝트(Repository)를 만듭니다 (예: `v-auto`). **이때 "README 생성" 체크박스는 해제하세요.**
2.  **연결 주소 확인**: 생성된 레포지토리의 주소(예: `https://github.com/사용자명/v-auto.git`)를 복사합니다.
3.  **서버에서 리모컨 등록**:
    ```bash
    # 복사한 주소를 'origin'이라는 이름의 리모컨으로 등록
    git remote add origin https://github.com/사용자명/v-auto.git

    # 원본 금고로 코드 밀어넣기 (Push)
    git push -u origin main
    ```

---

## 4. [3단계] 내 PC 세팅하기

이제 내 컴퓨터에서도 작업을 할 수 있게 준비합니다.

1.  **Git 설치**: PC에 Git이 설치되어 있어야 합니다.
2.  **코드 내려받기 (Clone)**:
    - PC의 터미널(또는 CMD)에서 코드를 두고 싶은 폴더로 이동합니다.
    ```bash
    git clone https://github.com/사용자명/v-auto.git
    cd v-auto
    ```
3.  **VS Code 설치**: VS Code로 이 폴더를 열면 훨씬 편하게 작업할 수 있습니다.

---

## 5. [4단계] 일상적인 작업 흐름 (Daily Workflow)

앞으로는 다음과 같은 순서로 작업하시면 가장 효율적이고 안전합니다.

### 1) 내 PC에서 작업 (수정)
- VS Code로 파일을 수정합니다 (예: `specs/web.yaml` 사양 변경)
- 수정이 끝나면 저장하고 기록을 남깁니다.
  ```bash
  git add .
  git commit -m "Update web spec: increase memory"
  git push origin main  # 금고(GitHub)로 업로드
  ```

### 2) 배포 서버에서 반영 (Pull)
- 실제 배포를 하기 위해 서버로 접속합니다.
- 금고에 있는 최신 코드를 서버로 끌어옵니다.
  ```bash
  cd /home/core/v-auto
  git pull origin main  # 최신 코드 동기화
  ```

### 3) 배포 실행
- 동기화된 코드로 배포를 수행합니다.
  ```bash
  python3 vm_manager.py samsung web deploy
  ```

---

## 💡 팁: VS Code Remote-SSH를 사용한다면?

만약 Git 작업이 너무 복잡하게 느껴지신다면, VS Code의 **Remote-SSH** 확장 프로그램을 강력 추천합니다.
- 서버에 직접 접속하여 내 폴더처럼 파일을 열 수 있습니다.
- VS Code 왼쪽의 **'소스 제어(Source Control)'** 아이콘을 클릭하면 명령어를 치지 않고도 마우스 클릭만으로 Git을 관리(Add, Commit, Push)할 수 있어 매우 직관적입니다.

---

**다음 단계로 무엇을 도와드릴까요?**
원하신다면 제가 현재 서버에서 `git init`과 `.gitignore` 설정을 지금 바로 수행해 드릴 수도 있습니다.
