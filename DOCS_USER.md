# v-auto v2.0 사용자 가이드 (User Guide)

> **대상 독자**: 서비스 개발자, 애플리케이션 운영자 (Tenant)  
> **목표**: 인프라 복잡성 없이, 원하는 서버(VM)를 정의하고 배포한다.

---

## 1. 5분 안에 시작하기 (Quick Start)

터미널에서 바로 따라 해보세요.

### 1️⃣ 배포 (Deploy)
"opasnet 프로젝트의 web 스펙을 배포해줘."
```bash
python3 vm_manager.py opasnet web deploy
```
> **팁**: 실행하면 비밀번호를 물어봅니다. 배포할 VM의 관리자 `admin` 계정 비밀번호를 입력하세요.

### 2️⃣ 확인 (Status)
"내 서버 잘 떴니? IP는 뭐야?"
```bash
python3 vm_manager.py opasnet web status
```

### 3️⃣ 삭제 (Delete)
"이제 필요 없어. 다 지워줘."
```bash
python3 vm_manager.py opasnet web delete
```

---

## 2. 나만의 서버 정의하기 (Spec 작성)

여러분이 건드려야 할 파일은 딱 하나입니다: **`projects/내프로젝트/specs/서버이름.yaml`**

### 📝 작성 예시 (`web.yaml`)
아래 내용을 복사해서 쓰세요.

```yaml
# [1] 공통 스펙 (Common Configuration)
# 이 파일에 정의된 모든 VM이 공유하는 설정입니다.
common:
  image: "ubuntu-22.04"     # OS 이미지 (인프라 팀 제공)
  network: svc-net          # 네트워크 망 이름 (인프라 팀 제공)
  cpu: 2                    # 기본 CPU 코어 수
  memory: 4Gi               # 기본 메모리 크기
  disk_size: 20Gi           # 기본 디스크 크기

  # [중요] VM 내부 설정 (Cloud-Init)
  cloud_init:
    # 1. 사용자 계정 생성
    users:
      - name: my-service-admin          # 계정 ID
        passwd: "{{ password | hash_password }}" # 비밀번호 (배포 시 물어봄 + 자동 암호화)
        shell: /bin/bash
        groups: [sudo]                  # sudo 권한 부여

    # 2. 필요한 패키지 설치
    packages:
      - nginx
      - curl

    # 3. 부팅 후 실행할 명령어
    runcmd:
      - systemctl enable --now nginx
      - echo "Hello v-auto" > /var/www/html/index.html

# [2] 인스턴스 리스트 (Instances)
# 실제로 찍어낼 서버들을 명확하게 나열합니다.
instances:
  - name: web-01            # 첫 번째 서버 이름
    ip: 10.215.100.101      # 고정 IP (필수)

  - name: web-02            # 두 번째 서버 이름
    ip: 10.215.100.102
    cpu: 4                  # (선택) 얘만 고사양으로 변경!
```

---

## 3. 핵심 개념 설명 (Concept)

### 💡 "인스턴스 리스트"가 뭔가요?
옛날에는 "서버 3개 줘!"라고 모호하게 말했다면, v2.0부터는 **"철수(IP .5), 영희(IP .6)"** 처럼 이름을 딱 정해서 요청해야 합니다.
`instances` 항목에 리스트를 추가하면 서버가 늘어나고, 지우면 서버가 삭제됩니다.

### 💡 네트워크 설정은 어디 갔나요?
복잡한 IP, 게이트웨이, DNS 설정은 **툴이 알아서 해줍니다.**
여러분은 그저 `network: 망이름`과 `ip: 주소`만 적으세요. 나머지는 자동입니다.

### 💡 비밀번호는 어떻게 넣나요?
설정 파일에 비밀번호를 평문으로 적으면 해킹당합니다.
`passwd: "{{ my_pw | hash_password }}"`라고 적어두면, 배포할 때 툴이 **"my_pw 입력하세요:"** 라고 물어보고, 자동으로 암호화해서 넣어줍니다.

---

## 4. 자주 묻는 질문 (FAQ)

**Q. OS 이미지는 어떤 게 있나요?**
A. 운영팀 공지사항이나 `infrastructure/images.yaml` (읽기 전용) 파일을 확인해보세요.

**Q. 특정 서버 하나만 다시 배포하고 싶어요.**
A. `--target` 옵션을 쓰세요. 나머지는 건드리지 않고 딱 걔만 고칩니다.
```bash
python3 vm_manager.py opasnet web deploy --target web-02
```
