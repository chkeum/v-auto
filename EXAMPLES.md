# v-auto 실무 시나리오별 예제 가이드 (Scenario Examples)

본 문서는 실무에서 마주칠 수 있는 다양한 요구사항을 `v-auto` 설정을 통해 어떻게 구현하는지 구체적인 예시와 함께 안내합니다.

---

## Case 1. 가장 기본적인 웹 서버 배포 (Default Network)

별도의 네트워크 설정 없이, 인프라의 기본 설정(DHCP 등)을 그대로 사용하여 1대를 배포하는 가장 기초적인 예제입니다.

### [config.yaml]
```yaml
namespace: vm-demo
storage_class: ocs-storagecluster-ceph-rbd  # 환경에 맞는 SC 지정
```

### [specs/simple-web.yaml]
```yaml
name_prefix: simple-web
replicas: 1
cpu: 1
memory: 2Gi
image_url: "http://internal-server/ubuntu.qcow2"
```

---

## Case 2. 고성능 DB 서버 일괄 배포 (Static IP 자동 계산)

폐쇄망에서 IP 충돌 없이 여러 대의 DB 서버를 띄워야 할 때 유용합니다. 툴이 자동으로 IP를 계산하여 주입합니다.

### [config.yaml]
```yaml
networks:
  db-net:
    bridge: br-db
    ipam:
      range: "192.168.10.0/24"  # 툴이 이 대역의 .101부터 순차적으로 할당
      gateway: "192.168.10.1"
```

### [specs/db-cluster.yaml]
```yaml
name_prefix: db-node
replicas: 3  # 실행 시 db-node-01(..101), -02(..102), -03(..103)으로 생성됨
cpu: 4
memory: 16Gi
image_url: "http://internal-server/rhel9.qcow2"
# Cloud-init에서 {{ static_ip }} 변수를 사용하여 내부 IP 자동 설정
cloud_init: |
  #cloud-config
  write_files:
    - path: /etc/netplan/01-static.yaml
      content: |
        network:
          version: 2
          ethernets:
            eth0:
              addresses: [{{ static_ip }}]
              gateway4: 192.168.10.1
```

---

## Case 3. 멀티 NIC 구성 (Service + Management)

내부망 관리 채널과 외부망 서비스 채널을 동시에 가져가야 하는 보안 환경용 설정입니다.

### [config.yaml]
```yaml
networks:
  mgmt-net: { bridge: br-mgmt, ipam: { range: "10.0.0.0/24" } }
  svc-net:  { bridge: br-svc,  ipam: { range: "172.16.0.0/24" } }
```

### [specs/secure-app.yaml]
```yaml
name_prefix: secure-app
networks:
  - mgmt-net  # 첫 번째 랜카드
  - svc-net   # 두 번째 랜카드
# ... 나머지 스펙 생략
```

---

## Case 4. 사용자 정의 커스텀 배포 (Cloud-Init 권한 설정)

비밀번호를 환경변수로 숨기고, 부팅 시 특정 패키지를 설치하거나 스크립트를 실행해야 하는 경우입니다.

### [specs/custom.yaml]
```yaml
cloud_init: |
  #cloud-config
  ssh_pwauth: True
  users:
    - name: tech-support
      passwd: {{ password }} # 실행 시 export PASSWORD=...로 주입
      sudo: ALL=(ALL) NOPASSWD:ALL
  runcmd:
    - mkdir -p /app/data
    - systemctl restart nginx
```

---
*모든 예제는 `projects/[프로젝트명]/specs/` 아래에 저장하여 즉시 실행 가능합니다.*
