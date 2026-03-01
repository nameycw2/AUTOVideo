#!/bin/bash
# 云服务器一键更新脚本
# 用法：PROJECT_DIR=/你的项目根目录 bash update.sh
# 项目根目录：包含 center_code/ 的那一层（例如 /var/www/autovideo_new）
set -e
PROJECT_DIR="${PROJECT_DIR:-/var/www/autovideo_new}"
cd "$PROJECT_DIR"
echo ">>> 项目目录: $PROJECT_DIR"
echo ">>> 拉取最新代码..."
git pull origin main || git pull origin master || true
echo ">>> 安装后端依赖..."
cd center_code/backend && pip install -r requirements.txt -q
echo ">>> 安装前端依赖并构建..."
cd "$PROJECT_DIR/center_code/frontend" && npm install --silent && npm run build
echo ">>> 重启后端（请根据实际方式执行其一）..."
cd "$PROJECT_DIR/center_code/backend"
echo "    若使用 systemd: sudo systemctl restart autovideo"
echo "    若使用 nohup:  pkill -f 'python app.py' 2>/dev/null; nohup python app.py 8081 > /tmp/backend.log 2>&1 &"
echo ">>> 更新完成。请手动执行上述重启命令后访问 http://你的服务器IP:8081"
