#!/bin/bash
# GMO Bot デプロイスクリプト
# 使用方法: ./deploy.sh <server_ip> <ssh_user>

set -e

SERVER=${1:-"your_server_ip"}
SSH_USER=${2:-"ubuntu"}
REMOTE_DIR="/home/${SSH_USER}/gmo-bot"

echo "=== GMO Bot Deployment Script ==="
echo "Server: ${SERVER}"
echo "User: ${SSH_USER}"
echo "Remote directory: ${REMOTE_DIR}"

# 1. ローカルでリリースビルド
echo ""
echo "=== Step 1: Building release binary ==="
cargo build --release --bin gmo

# 2. 必要なファイルをサーバーに転送
echo ""
echo "=== Step 2: Uploading files to server ==="
ssh ${SSH_USER}@${SERVER} "mkdir -p ${REMOTE_DIR}/src"

rsync -avz --progress \
    ./target/release/gmo \
    ${SSH_USER}@${SERVER}:${REMOTE_DIR}/

rsync -avz --progress \
    ./src/trade-config.yaml \
    ${SSH_USER}@${SERVER}:${REMOTE_DIR}/src/

rsync -avz --progress \
    ./deploy/gmo-bot.service \
    ${SSH_USER}@${SERVER}:/tmp/

# 3. サーバー側でサービスを設定
echo ""
echo "=== Step 3: Setting up systemd service ==="
ssh ${SSH_USER}@${SERVER} << 'ENDSSH'
sudo mv /tmp/gmo-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable gmo-bot
echo "Service installed. Configure environment variables before starting."
echo ""
echo "To set API keys, edit /etc/systemd/system/gmo-bot.service:"
echo "  sudo systemctl edit gmo-bot"
echo ""
echo "Add:"
echo "[Service]"
echo "Environment=\"GMO_API_KEY=your_key\""
echo "Environment=\"GMO_API_SECRET=your_secret\""
echo ""
echo "Then start:"
echo "  sudo systemctl start gmo-bot"
echo "  sudo systemctl status gmo-bot"
ENDSSH

echo ""
echo "=== Deployment complete! ==="
