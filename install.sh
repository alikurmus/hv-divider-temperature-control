#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/hv-divider-pid
ENV_DIR="$APP_DIR/conda-env"
CONFIG_DIR=/etc/hv-divider-pid
LOG_DIR=/var/log/hv-divider-pid
SERVICE=/etc/systemd/system/hv-divider-pid.service

# Run this script as your normal Miniforge user. It invokes sudo only for
# system-level operations. Do not run the whole script with sudo.
if [[ ${EUID} -eq 0 ]]; then
    echo "Run ./install.sh as your normal user, not with sudo." >&2
    exit 1
fi

INSTALL_USER=${SUDO_USER:-$USER}
INSTALL_HOME=$(getent passwd "$INSTALL_USER" | cut -d: -f6)

find_conda() {
    local candidate
    if [[ -n "${CONDA_EXE:-}" && -x "${CONDA_EXE}" ]]; then
        printf '%s\n' "$CONDA_EXE"
        return 0
    fi
    if command -v conda >/dev/null 2>&1; then
        command -v conda
        return 0
    fi
    for candidate in \
        "$INSTALL_HOME/miniforge3/bin/conda" \
        "$INSTALL_HOME/mambaforge/bin/conda" \
        "$INSTALL_HOME/Miniforge3/bin/conda"; do
        if [[ -x "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

if ! CONDA_BIN=$(find_conda); then
    echo "Could not find Miniforge/Conda." >&2
    echo "Activate Miniforge first or install it in ~/miniforge3." >&2
    exit 1
fi

echo "Using Conda executable: $CONDA_BIN"

sudo apt-get update
sudo apt-get install -y i2c-tools python3-dev

# Enable hardware buses on Raspberry Pi OS.
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0

if ! id pidbox >/dev/null 2>&1; then
    sudo useradd --system --create-home --shell /usr/sbin/nologin pidbox
fi
sudo usermod -a -G gpio,spi,i2c pidbox

sudo mkdir -p "$APP_DIR" "$CONFIG_DIR" "$LOG_DIR"
sudo cp standalone_hv_divider_pid.py requirements.txt "$APP_DIR"/
if [[ ! -f "$CONFIG_DIR/config.toml" ]]; then
    sudo cp config.toml "$CONFIG_DIR/config.toml"
fi
sudo cp hv-divider-pid.service "$SERVICE"

# Let the Miniforge user create the environment in /opt, then transfer
# ownership to the dedicated service account.
sudo chown -R "$INSTALL_USER":"$INSTALL_USER" "$APP_DIR"

if [[ ! -x "$ENV_DIR/bin/python" ]]; then
    "$CONDA_BIN" create --yes --prefix "$ENV_DIR" python=3.11 pip
fi

"$CONDA_BIN" run --prefix "$ENV_DIR" \
    python -m pip install --upgrade pip
"$CONDA_BIN" run --prefix "$ENV_DIR" \
    python -m pip install -r "$APP_DIR/requirements.txt"

sudo chown -R pidbox:pidbox "$APP_DIR" "$LOG_DIR"
sudo chown root:pidbox "$CONFIG_DIR/config.toml"
sudo chmod 640 "$CONFIG_DIR/config.toml"

sudo systemctl daemon-reload

# Do not automatically enable or start heater control during installation.
echo "Installed with Conda environment: $ENV_DIR"
echo "Edit $CONFIG_DIR/config.toml and test simulation mode first:"
echo "  sudo -u pidbox $ENV_DIR/bin/python $APP_DIR/standalone_hv_divider_pid.py --config $CONFIG_DIR/config.toml --simulate"
echo "After hardware commissioning:"
echo "  sudo systemctl start hv-divider-pid"
echo "  sudo systemctl enable hv-divider-pid"
echo "  sudo journalctl -u hv-divider-pid -f"
