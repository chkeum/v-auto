#!/bin/bash

# VM 자동 배포 툴 폐쇄망 번들링 자동화 스크립트
# 사용법: ./bundle.sh [버전태그(예: v1.0.1)]

VERSION=${1:-"v$(date +%Y%m%d)"}
REPO_NAME="v-auto"
BUNDLE_NAME="${REPO_NAME}-packaged.tar.gz"
RELEASE_DIR="releases"

echo "=== [1/4] 의존성 패키지 확인 ==="
if [ ! -d "packages" ] || [ -z "$(ls -A packages)" ]; then
    echo "Error: 'packages' 폴더가 비어있습니다. 먼저 'pip download'를 수행하십시오."
    exit 1
fi

echo "=== [2/4] 폐쇄망용 번들 압축 (venv 등 제외) ==="
cd ..
# 제외할 목록 정의
EXCLUDES=(
    "${REPO_NAME}/venv"
    "${REPO_NAME}/.venv"
    "${REPO_NAME}/.git"
    "${REPO_NAME}/.gitignore"
    "${REPO_NAME}/releases"      # 과거 릴리즈 파일 배제 (용량 절감 핵심)
    "${REPO_NAME}/.vscode"      # 에디터 설정 배제
    "${REPO_NAME}/.idea"
    "${REPO_NAME}/*.sh"         # 패키징/싱크 스크립트 배제 (Bastion 미사용)
    "${REPO_NAME}/*.md"         # 가이드/문서 배제 (순수 코드 패키지 지향)
    "*/__pycache__"
    "*.DS_Store"
)

# Tar 명령어 조립
TAR_CMD="tar"
for item in "${EXCLUDES[@]}"; do
    TAR_CMD+=" --exclude=\"$item\""
done

eval "$TAR_CMD -cvzf \"${BUNDLE_NAME}\" \"${REPO_NAME}/\""

echo "=== [3/4] 릴리즈 폴더 정리 ==="
cd "${REPO_NAME}"
mkdir -p "${RELEASE_DIR}"
mv "../${BUNDLE_NAME}" "${RELEASE_DIR}/"

echo "=== [4/4] Git 업로드 (Commit & Push) ==="
git add "${RELEASE_DIR}/${BUNDLE_NAME}"
git commit -m "Release offline bundle ${VERSION}"
git push origin main

echo "=========================================="
echo "번들링 및 업로드가 완료되었습니다: ${VERSION}"
echo "Bastion 다운로드 경로: releases/${BUNDLE_NAME}"
echo "=========================================="
