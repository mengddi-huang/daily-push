#!/usr/bin/env bash
# 一键把 daily_push 项目推到 GitHub 仓库
# 使用方法：
#   bash deploy_to_github.sh <github_repo_url>
# 例如：
#   bash deploy_to_github.sh git@github.com:yourname/daily-push.git
#   bash deploy_to_github.sh https://github.com/yourname/daily-push.git
#
# 执行前请先：
#   1. 在 GitHub 创建一个新仓库（public 或 private 都行）
#   2. 将仓库 URL 作为参数传入
#   3. 执行完成后，去仓库 Settings → Secrets 添加 WEBHOOK_URL
#   4. 去 Settings → Pages 开启：Source = main / 目录 /docs
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "用法: bash deploy_to_github.sh <github_repo_url>"
  echo "  示例: bash deploy_to_github.sh git@github.com:yourname/daily-push.git"
  exit 1
fi

REPO_URL="$1"
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo ">> 初始化 git 仓库..."
if [ ! -d .git ]; then
  git init -b main
fi

echo ">> 添加文件..."
git add .
git status --short

echo ">> 创建首次 commit..."
if git diff --staged --quiet; then
  echo "    无新改动"
else
  git commit -m "init: daily push automation" || true
fi

echo ">> 配置 remote..."
if git remote | grep -q "^origin$"; then
  git remote set-url origin "$REPO_URL"
else
  git remote add origin "$REPO_URL"
fi

echo ">> 推送到 GitHub..."
git push -u origin main

cat <<EOF

================================================================
✅ 推送完成！下一步请手动配置 GitHub：

1. 进入仓库 → Settings → Secrets and variables → Actions
   → New repository secret
   Name:  WEBHOOK_URL
   Value: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<你的key>

2. 进入 Settings → Pages
   Source: "Deploy from a branch"
   Branch: main    Folder: /docs
   保存后等待 1 分钟，会显示 Pages 地址

3. 进入 Actions 标签 → 选 "Daily Push" → Run workflow（手动触发一次测试）

完成后每天北京时间 10:00 自动推送 🎉
================================================================
EOF
