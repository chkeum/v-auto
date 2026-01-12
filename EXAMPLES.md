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

## Case 5. 고급 스케줄링 배치 (Node Selection & Affinity)

하드웨어 특성이나 가용성 요구사항에 따라 VM의 배치 위치를 세밀하게 제어하는 예제입니다.

### [specs/advanced-scheduling.yaml]
```yaml
name_prefix: high-perf-vm

# 1. 다중 Node Selector (AND 조건: 모든 라벨이 일치해야 함)
node_selector:
  region: "seoul-zone-1"
  storage: "ssd"
  gpu: "enbaled"

# 2. Node Affinity (유연한 규칙: 선호도 또는 필수 조건)
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: "rack"
          operator: "In"
          values: ["rack-01", "rack-02"]
```

---

## Case 6. 특정 인스턴스 핀포인트 복구 (Pinpoint Recovery)

운영 중 `web-02`만 손상되어 삭제한 후, 해당 번호와 IP(.102)를 그대로 유지하며 다시 배포하고 싶을 때 사용합니다. 또는 기존 범위를 벗어나 `web-04`만 단독 추가할 때도 유용합니다.

### 실행 방법
```bash
# web-02만 콕 집어서 동일한 설정으로 복구
python3 vm_manager.py samsung web deploy --target web-02

# 기존 replicas가 2대더라도, web-04를 단독으로 추가 생성 (IP는 자동으로 .104 할당)
python3 vm_manager.py samsung web deploy --target web-04
```

---
*모든 예제는 `projects/[프로젝트명]/specs/` 아래에 저장하여 즉시 실행 가능합니다.*
