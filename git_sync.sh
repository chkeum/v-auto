#!/bin/bash

# VM 자동 배포 툴 Git 동기화 및 배포 패키지 갱신 자동화 스크립트
# 사용법: ./git_sync.sh [커밋 메시지]

MESSAGE=${1:-"Update source and refresh deployment package $(date +'%Y-%m-%d %H:%M:%S')"}
REPO_NAME="v-auto"
BUNDLE_NAME="${REPO_NAME}-packaged.tar.gz"
RELEASE_DIR="releases"

echo "=== [0/3] 새로운 배포 번들 생성 (Generating Bundle) ==="
# 제외 및 압축 로직 (bundle.sh와 동일하게 유지하여 일관성 확보)
EXCLUDES=(
    "${REPO_NAME}/venv"
    "${REPO_NAME}/.venv"
    "${REPO_NAME}/.git"
    "${REPO_NAME}/.gitignore"
    "${REPO_NAME}/${RELEASE_DIR}"
    "${REPO_NAME}/.vscode"
    "${REPO_NAME}/.idea"
    "${REPO_NAME}/*.sh"
    "${REPO_NAME}/*.md"
    "*/__pycache__"
    "*.DS_Store"
)

# 부모 디렉토리로 이동하여 압축 수행
cd ..
TAR_CMD="tar"
for item in "${EXCLUDES[@]}"; do
    TAR_CMD+=" --exclude=\"$item\""
done

# 압축 실행
eval "$TAR_CMD -czf \"${BUNDLE_NAME}\" \"${REPO_NAME}/\""

# 다시 툴 디렉토리로 복귀
cd "${REPO_NAME}"
mkdir -p "${RELEASE_DIR}"
mv "../${BUNDLE_NAME}" "${RELEASE_DIR}/"
echo "[OK] 최신 배포 패키지가 생성되었습니다: ${RELEASE_DIR}/${BUNDLE_NAME}"

echo "=== [1/3] 변경 사항 스테이징 (git add .) ==="
# 패키지 파일을 포함하여 모든 소스 및 문서 변경 사항을 스테이징합니다.
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
echo "동기화 및 배포 패키지 갱신이 완료되었습니다!"
echo "커밋 메시지: $MESSAGE"
echo "다운로드 경로: ${RELEASE_DIR}/${BUNDLE_NAME}"
echo "=========================================="
