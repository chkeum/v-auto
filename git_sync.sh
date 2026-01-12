#!/bin/bash

# VM 자동 배포 툴 Git 동기화 자동화 스크립트
# 사용법: ./sync.sh [커밋 메시지]

MESSAGE=${1:-"Update source and dependencies $(date +'%Y-%m-%d %H:%M:%S')"}

echo "=== [1/3] 변경 사항 스테이징 (git add .) ==="
# 추가, 수정, 삭제된 모든 파일을 포함합니다.
git add .

# 변경 사항이 있는지 확인
if git diff --cached --quiet; then
    echo "변경 사항이 없습니다. 작업을 종료합니다."
    exit 0
fi

echo "=== [2/3] 변경 사항 커밋 ==="
git commit -m "$MESSAGE"

echo "=== [3/3] 원격 저장소로 푸시 ==="
git push origin main

echo "=========================================="
echo "동기화가 완료되었습니다!"
echo "커밋 메시지: $MESSAGE"
echo "=========================================="
