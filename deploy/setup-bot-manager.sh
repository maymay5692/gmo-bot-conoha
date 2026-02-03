#!/bin/bash
# Bot Manager Setup Script for VPS
# Run as ubuntu user (not root)

set -e

BOT_DIR="/home/ubuntu/gmo-bot"
MANAGER_DIR="$BOT_DIR/bot-manager"
ENV_FILE="/etc/bot-manager.env"

echo "=== GMO Bot Manager Setup ==="

# 1. Create virtual environment
echo "[1/6] Creating virtual environment..."
cd "$MANAGER_DIR"
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
echo "[2/6] Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 3. Setup authentication (requires root)
echo "[3/6] Setting up authentication..."
if [ ! -f "$ENV_FILE" ]; then
    # Generate random password
    ADMIN_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

    sudo tee "$ENV_FILE" > /dev/null << EOF
ADMIN_USER=admin
ADMIN_PASS=$ADMIN_PASS
SECRET_KEY=$SECRET_KEY
EOF
    sudo chmod 600 "$ENV_FILE"
    sudo chown root:root "$ENV_FILE"

    echo ""
    echo "=========================================="
    echo "IMPORTANT: Save these credentials!"
    echo "Username: admin"
    echo "Password: $ADMIN_PASS"
    echo "=========================================="
    echo ""
else
    echo "Credentials file already exists at $ENV_FILE"
fi

# 4. Setup sudoers for systemctl (requires root)
echo "[4/6] Setting up sudoers..."
sudo tee /etc/sudoers.d/gmo-bot > /dev/null << 'EOF'
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl start gmo-bot
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl stop gmo-bot
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart gmo-bot
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl status gmo-bot
EOF
sudo chmod 440 /etc/sudoers.d/gmo-bot

# 5. Install systemd service
echo "[5/6] Installing systemd service..."
sudo cp "$BOT_DIR/deploy/bot-manager.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bot-manager

# 6. Start service
echo "[6/6] Starting Bot Manager..."
sudo systemctl start bot-manager

echo ""
echo "=== Setup Complete ==="
echo "Bot Manager is running at: http://127.0.0.1:5000"
echo ""
echo "Commands:"
echo "  sudo systemctl status bot-manager  - Check status"
echo "  sudo systemctl restart bot-manager - Restart"
echo "  journalctl -u bot-manager -f       - View logs"
echo ""
echo "To view credentials: sudo cat $ENV_FILE"
