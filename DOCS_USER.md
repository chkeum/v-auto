# v-auto v2.0 사용자 가이드 (User Guide)

> **대상 독자**: 서비스 개발자, 애플리케이션 운영자 (Tenant)  
> **목표**: 인프라 복잡성 없이, 원하는 서버(VM)를 정의하고 배포한다.

---

## 1. 5분 안에 시작하기 (Quick Start)

터미널에서 바로 따라 해보세요.

### 1️⃣ 설정 확인 (Inspect)
"내 서버가 어떻게 배포될지 미리 보고 싶어."
```bash
./vman opasnet web inspect
```

### 2️⃣ 배포 (Deploy)
"opasnet 프로젝트의 web 스펙을 배포해줘."
```bash
./vman opasnet web deploy
```
> **팁 1**: 실행하면 비밀번호를 물어봅니다. 배포할 VM의 관리자 `admin` 계정 비밀번호를 입력하세요.
> **팁 2**: `--dry-run` 옵션을 붙이면 실제로 배포하지 않고, 생성될 YAML 파일(Template 결과)만 출력해줍니다.

### 3️⃣ 확인 (Status)
"내 서버 잘 떴니? IP는 뭐야?"
```bash
./vman opasnet web status
```

### 4️⃣ 삭제 (Delete)
"이제 필요 없어. 다 지워줘."
```bash
./vman opasnet web delete
```

---

## 2. 나만의 서버 정의하기 (Spec 작성)

여러분이 건드려야 할 파일은 딱 하나입니다: **`projects/내프로젝트/서버이름.yaml`**

### 📝 작성 예시 (`web.yaml`)
아래 내용을 복사해서 쓰세요.

```yaml
# [0] 인프라 정의 (Infrastructure)
# 네트워크와 이미지를 여기서 직접 정의합니다. (All-in-One Spec)
infrastructure:
  networks:
    default:
      bridge: br-virt
      nad_name: br-virt-net
      ipam:
        type: whereabouts
        range: 10.215.100.0/24
        gateway: 10.215.100.1
      dns: [8.8.8.8]

  images:
    ubuntu-22.04:
      url: "http://10.215.1.240/vm-images/ubuntu/ubuntu-22.04.qcow2"
      min_cpu: 1
      min_mem: 1Gi

# [1] 공통 스펙 (Common Configuration)
# 이 파일에 정의된 모든 VM이 공유하는 설정입니다.
common:
  image: "ubuntu-22.04"     # 위에서 정의한 이미지 참조
  network: default          # 위에서 정의한 네트워크 참조
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
./vman opasnet web deploy --target web-02
```

---

## 📸 부록: 실제 실행 예시 (Appendix)

다음은 실제 운영 환경에서 `delete`, `deploy`, `status` 명령어를 연속으로 수행한 결과 로그입니다.

### 1️⃣ 삭제 (Cleanup)
```text
$ ./vman opasnet web delete
Gathering resources for deletion in namespace 'vm-opasnet'...
Are you sure you want to proceed with deletion? [y/N]: y
Starting deletion process...
  [SUCCESS] Managed resources deleted.
[OK] Cleanup complete for Spec 'web'.
```

### 2️⃣ 배포 (Deploy) - v2.0
```text
$ ./vman opasnet web deploy --yes
Loading configuration for Project: opasnet, Spec: web...

==================================================
 [ Deployment Configuration Summary (v2.0) ] 
==================================================
 Project   : opasnet
 Spec      : web
 Namespace : vm-opasnet
 Instances : 1
   - web-01 (IP: 10.215.100.101)
--------------------------------------------------
 Base Interfaces (Infra Managed):
  NIC 0: Type=multus, NAD=br-virt-net, Subnet=10.215.100.0/24
==================================================

    [Net-Inject] web-01: Static IP 10.215.100.101 on injected NAD web-01-br-virt-net

>>> Preparing Instance: web-01
Applying resources for web-01...
--> web-01 Deployed.

==================================================
 [ Final Status Summary ]
==================================================
1. Managed Virtual Machines (Health & Power)
   - web-01               Running                -         true
```

### 3️⃣ 상태 확인 (Status)
```text
$ ./vman opasnet web status

[ Detailed Status Diagnostic: opasnet/web ]
Target Namespace: vm-opasnet
====================================================================================================

1. Managed Virtual Machines (Health & Power)
----------------------------------------------------------------------------------------------------
NAME                    STATUS                 READY     RUNNING
web-01                  Running                True      true

2. Active Runtime & IP Addresses (VMI / Pod)
----------------------------------------------------------------------------------------------------
NAME                    IP                  NODE
web-01                  10.215.100.101      worker-1.ocp.local

3. Storage & Disk Provisioning (DataVolumes / PVC)
----------------------------------------------------------------------------------------------------
NAME                    PHASE       PROGRESS    ACCESS-MODES
web-01-root-disk        Succeeded   100.0%      [ReadWriteOnce]
====================================================================================================
```
