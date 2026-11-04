# How to Run the Repository

The repository has two distinct uses:

1. **Laptop mode:** run the thermal simulation and the interactive Jupyter notebook.
2. **Raspberry Pi mode:** install, commission, and operate the standalone
   hardware controller.

Both use Miniforge/Conda. `mamba` may be substituted for `conda` in the laptop
commands.

Do not run `install.sh` on a Mac. It is for 64-bit Raspberry Pi OS and uses
`apt-get`, `raspi-config`, GPIO, SPI, I²C, and `systemd`.

Hardware choices (heater, current driver, parts) are described in
[`docs/HEATER_AND_CURRENT_DRIVER.md`](docs/HEATER_AND_CURRENT_DRIVER.md) and
[`ORDER_LIST.md`](ORDER_LIST.md).

## Repository contents

```text
.
├── README.md
├── HOW_TO_RUN.md
├── WIRING_AND_BOM.md
├── ORDER_LIST.md
├── TODO.md                    # explicit task list, phase by phase
├── environment.yml            # laptop Conda environment (conda-forge only)
├── config.toml                # controller configuration (default: simulate)
├── standalone_hv_divider_pid.py
├── requirements.txt           # Raspberry Pi hardware libraries (pip)
├── install.sh                 # Raspberry Pi installer
├── hv-divider-pid.service     # systemd unit
├── notebooks/
│   └── PID_Control_Toy_Simulation.ipynb
├── docs/
│   ├── HV_Divider_Standalone_PID_System_Description.md
│   ├── HEATER_AND_CURRENT_DRIVER.md
│   ├── SYSTEM_DESIGN_AND_WIRING.md   # architecture, pin-by-pin wiring
│   └── 2026-08-11_feedback_response.md
└── legacy/
    ├── cryogenic_pid_loop_v2.py
    └── slow_controls_thermal_pid_controller.py
```

---

# Part A — Laptop (macOS or Linux)

## A1. Create the Conda environment

From the repository root:

```bash
conda env create -f environment.yml
conda activate hv-divider-pid
```

If the environment already exists and `environment.yml` changed (it did in this
revision: the Anaconda `defaults` channel was removed):

```bash
conda env update -f environment.yml --prune
conda activate hv-divider-pid
```

Confirm the interpreter and the notebook packages:

```bash
which python
python --version      # 3.11.x
python -c "import numpy, matplotlib, ipywidgets, ipympl; print('env OK')"
```

## A2. Run the standalone thermal simulation

From the repository root, with the environment active:

```bash
python standalone_hv_divider_pid.py \
  --config config.toml \
  --simulate
```

One status line is printed per second. Stop with `Ctrl+C`; the controller
commands zero current and exits cleanly.

`--simulate` forces the simulated plant, disables the LCD, and writes data to
`./controller_simulation.csv` in the **current directory**. The file is
**appended** on every run (delete it to start fresh) and is ignored by Git.

The simulation runs in real time. With the default toy-model parameters it
takes several hours to settle, and the default gains overshoot to about
29.7 °C before settling at 28 °C. That is a property of the placeholder gains,
not the hardware; use the notebook to explore gains quickly.

## A3. Run the interactive notebook

Register the environment as a Jupyter kernel once:

```bash
conda activate hv-divider-pid
python -m ipykernel install --user \
  --name hv-divider-pid \
  --display-name "HV Divider PID"
```

Start JupyterLab from the same environment:

```bash
jupyter lab notebooks/PID_Control_Toy_Simulation.ipynb
```

Select the **HV Divider PID** kernel if it is not selected automatically and
run the cells top to bottom. The `ipywidgets` sliders then vary the toy-model
parameters.

The notebook uses the interactive Matplotlib backend from `ipympl`
(`%matplotlib widget`, equivalently `%matplotlib ipympl`).

### Fix a missing Matplotlib widget backend

```text
RuntimeError: 'widget' is not a recognised backend name
```

means `ipympl` is missing from the kernel's environment:

```bash
conda activate hv-divider-pid
conda install -c conda-forge ipympl
```

Restart the kernel. If JupyterLab was started before the install, stop it and
start it again from the `hv-divider-pid` environment. Check with:

```bash
python -c "import ipympl, ipywidgets, matplotlib; print('ipympl', ipympl.__version__); print('ipywidgets', ipywidgets.__version__); print('matplotlib', matplotlib.__version__)"
```

If JupyterLab and the kernel deliberately live in different environments,
install `ipympl` in the kernel environment and `jupyterlab_widgets` in the
JupyterLab environment. Launching JupyterLab from `hv-divider-pid` avoids this.

## A4. Remove and rebuild the laptop environment

```bash
conda deactivate
conda env remove --name hv-divider-pid
conda env create -f environment.yml
conda activate hv-divider-pid
```

---

# Part B — Raspberry Pi controller

## B1. Prerequisites

- Raspberry Pi 4 Model B (recommended), Pi 5, or Pi Zero 2 W.
- **64-bit** Raspberry Pi OS (Bookworm or Trixie), Lite is fine. Miniforge
  does not support 32-bit ARM, and `install.sh` stops if `uname -m` is not
  `aarch64`.
- Network access for the first install (GitHub, conda-forge, PyPI).
- Hardware wired per `docs/SYSTEM_DESIGN_AND_WIRING.md` (pin-by-pin tables)
  and `docs/HEATER_AND_CURRENT_DRIVER.md`. Nothing needs to be connected to
  run the simulation in B5.

Pin and address summary used by the default `config.toml`:

| Function | Pi pin (BCM) | Bus / address |
|---|---|---|
| MAX31865 SCK / SDI / SDO | GPIO11 / GPIO10 / GPIO9 | SPI0 (shared) |
| PT100 control_air CS (S1 air, PID) | GPIO5 (`D5`) | |
| PT100 monitor_air CS (S2 air, far side) | GPIO6 (`D6`) | |
| PT100 ground_board CS (S3 ground board) | GPIO13 (`D13`) | |
| PT100 spare CS (S4 heater plate) | GPIO19 (`D19`) | |
| I²C SDA / SCL | GPIO2 / GPIO3 | I²C-1 |
| MCP4725 DAC (Adafruit #935) | | `0x62` |
| INA260 | | `0x40` |
| SHT31-D (optional) | | `0x44` |
| 20x4 LCD, PCF8574 backpack | | `0x27` (some are `0x3F`) |
| Heater-enable relay | GPIO17 | active high |
| Fan enable / tach (optional) | GPIO27 / GPIO22 | |

## B2. Install Miniforge

```bash
uname -m        # must print: aarch64
sudo apt-get update && sudo apt-get install -y git curl
curl -L -O "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
bash "Miniforge3-$(uname)-$(uname -m).sh" -b -p "$HOME/miniforge3"
"$HOME/miniforge3/bin/conda" init bash
exec bash
conda --version
```

## B3. Clone and install

```bash
cd ~
git clone https://github.com/alikurmus/hv-divider-temperature-control.git
cd ~/hv-divider-temperature-control
```

Leave `mode = "simulate"` in `config.toml` for the first install. Run the
installer from the repository root as your normal user (it calls `sudo` only
where needed):

```bash
bash install.sh
```

The installer:

- installs `i2c-tools`, `python3-dev`, `libusb-1.0-0`;
- enables SPI and I²C;
- creates the `pidbox` service user (groups `gpio`, `spi`, `i2c`);
- copies the program to `/opt/hv-divider-pid/`, the config to
  `/etc/hv-divider-pid/config.toml` (only if none exists yet), and the unit
  file to `/etc/systemd/system/`;
- creates the Conda environment `/opt/hv-divider-pid/conda-env` (Python 3.11)
  and pip-installs `requirements.txt` into it;
- does **not** start or enable the service.

Reboot once so SPI and I²C are active:

```bash
sudo reboot
```

## B4. Check the buses and the Python environment

```bash
ls /dev/spidev0.0 /dev/i2c-1
i2cdetect -y 1
```

With the full I²C hardware connected, expect `27` (LCD), `40` (INA260), `62`
(MCP4725), and `44` if the SHT31-D is fitted. If an address differs, put the
observed value in `/etc/hv-divider-pid/config.toml`.

Check that the service user can import every hardware library and claim a GPIO
through `gpiozero` (this holds GPIO17 **low**, i.e. heater disabled):

```bash
cd /tmp
sudo -u pidbox /opt/hv-divider-pid/conda-env/bin/python -c "
import board, digitalio, adafruit_max31865, adafruit_mcp4725, adafruit_ina260, adafruit_sht31d
import RPLCD.i2c, pyvisa, gpiozero
d = gpiozero.OutputDevice(17, initial_value=False)
print('imports OK; gpiozero pin factory:', type(d.pin_factory).__name__)
d.close()"
```

Expected: `imports OK; gpiozero pin factory: LGPIOFactory`.

**Always `cd /tmp` (or another directory `pidbox` can write) before running
the program with `sudo -u pidbox`.** The `lgpio` GPIO backend and the
simulation CSV both write to the current directory; `pidbox` cannot write to
your home directory.

## B5. Run the installed simulation

```bash
cd /tmp
sudo -u pidbox \
  /opt/hv-divider-pid/conda-env/bin/python \
  /opt/hv-divider-pid/standalone_hv_divider_pid.py \
  --config /etc/hv-divider-pid/config.toml \
  --simulate
```

Stop with `Ctrl+C`. Data go to `/tmp/controller_simulation.csv`.

## B6. Commission the hardware (bench, divider HV off)

Do these steps in order. Each step is a foreground run so you can watch the
log and stop it with `Ctrl+C`. Make sure the service is not running at the same
time:

```bash
sudo systemctl stop hv-divider-pid 2>/dev/null || true
```

Edit the installed config with:

```bash
sudo nano /etc/hv-divider-pid/config.toml
```

The foreground command used in every step is:

```bash
cd /tmp
sudo -u pidbox \
  /opt/hv-divider-pid/conda-env/bin/python \
  /opt/hv-divider-pid/standalone_hv_divider_pid.py \
  --config /etc/hv-divider-pid/config.toml
```

Hardware runs log to `[logging] csv_path` (default
`/var/log/hv-divider-pid/controller.csv`, appended). Give each test its own
file, e.g. `csv_path = "/var/log/hv-divider-pid/2026-11-xx_fixed_5W.csv"`.
Copy logs to a laptop with
`scp <user>@<pi-host>:/var/log/hv-divider-pid/*.csv .`

A latched fault (`HEATER FAULT: ...`) disables the heater and **exits** the
program. Fix the cause and start it again.

### Step 1 — Sensors and display, heater locked at zero

Select the actuator you have and lock the output to zero:

```toml
[control]
max_power_w = 0.0
max_current_a = 0.0

[hardware]
mode = "dac"          # embedded DAC + linear current driver
# mode = "scpi"       # programmable bench supply (see B7)
use_ina260 = true     # false if no INA260 is fitted (scpi mode ignores it)
use_lcd = true        # false if no LCD is fitted
```

The program must be able to open the actuator (MCP4725 on I²C in `dac` mode,
or the supply over LAN/USB in `scpi` mode), but with these limits it is only
ever commanded to 0 A.

Check:

- all four PT100s read room temperature and agree within a few tenths of a
  degree (before calibration);
- the LCD shows a changing heartbeat character;
- **monitor-sensor fault:** unplug one lead of `monitor_air`, `ground_board`,
  or `spare` → a `Monitoring PT100 ... failed` warning appears and control
  continues; reconnect;
- **control-sensor fault:** unplug one lead of `control_air` →
  `HEATER FAULT: MAX31865 control_air fault: ...`, heater disabled, program
  exits.

### Step 2 — Heater path at fixed low power (open loop)

Measure the heater resistance with a 4-wire ohmmeter first. Then:

```toml
[control]
kp_w_per_c = 0.0
ki_w_per_c_s = 0.0
kd_w_s_per_c = 0.0
power_bias_w = 1.0            # fixed 1 W
max_power_w = 25.0            # rating of the installed heater
max_current_a = 1.05          # <= what the driver can deliver with headroom
heater_resistance_ohm = 20.0  # measured value

[hardware]
current_driver_full_scale_a = 1.32   # dac mode: as-built full scale (reference design: 1.32)
```

Check:

- the heater-enable relay closes only after 5 valid sensor readings and opens
  on `Ctrl+C`;
- `Icmd` and `Imeas` in the log agree. In `dac` mode, if they differ, set
  `current_driver_full_scale_a = old_value * Imeas / Icmd` and repeat;
- with the INA260 on the high side of a low-side current sink, the logged
  `measured_power_w` is the **24 V branch power** (24 V × I). Heater power is
  `Imeas² × heater_resistance_ohm`.

> **Heater-plate sensor (S4 on the `spare` channel).** The plate runs several
> kelvin above the air, so it will cross the 31 °C software trip in steps 3
> and 4. Until TODO S1 adds a per-sensor limit, set
> `trip_on_monitor_overtemperature = false` for supervised runs. S2–S4 then
> warn only; TS1 and TF1 still protect the plate in hardware.

### Step 3 — Fixed-power thermal tests (2, 5, 10 W)

Keep the gains at zero and set `power_bias_w` to `2.0`, then `5.0`, then
`10.0`. Run each until the temperatures stop changing (expect hours), with a
separate `csv_path` per run. From each run take the equilibrium rise ΔT, the
loss conductance `G = P / ΔT`, and the time constant τ (then `C = G·τ`).

The software over-temperature trip (`overtemperature_c = 31.0`) stays active.
At 10 W the enclosure may exceed 31 °C: either stop the run before it trips, or
raise `overtemperature_c` (e.g. to 40) **for that test only**, with the
hardware thermostat and thermal fuse installed.

### Step 4 — Closed-loop PI

Restore the control settings:

```toml
[control]
kp_w_per_c = 1.0                # starting value; tune
ki_w_per_c_s = 0.002            # starting value; tune
kd_w_s_per_c = 0.0
power_bias_w = 0.0              # or the steady-state power found in step 3
overtemperature_c = 31.0
```

Setting `power_bias_w` to the measured steady-state power at 28 °C
(`G × (28 − T_room)`) reduces the warm-up overshoot. Tune per the
characterization plan (P first, then I, `Kd = 0`), watching
`ripple_pp` and `status` (`RAMP` → `WAIT` → `STABLE`).

## B7. Actuator-specific settings

### `mode = "dac"` (MCP4725 + current driver)

- `dac_i2c_address = 0x62` for the Adafruit MCP4725 (#935).
- `current_driver_full_scale_a` = driver current at DAC full scale (3.3 V).
- `output_enable_gpio = 17` drives the normally-open heater relay.
- `use_ina260 = true` for current/voltage readback.

### `mode = "scpi"` (programmable bench supply)

Use LAN (VXI-11) if possible: it needs no extra drivers or permissions. Example
for a Siglent SPD1305X (check the commands against your supply's manual):

```toml
[hardware]
mode = "scpi"
visa_resource = "TCPIP0::192.168.1.50::INSTR"
scpi_set_current = "CH1:CURRent {value:.3f}"
scpi_output_on = "OUTPut CH1,ON"
scpi_output_off = "OUTPut CH1,OFF"
scpi_measure_current = "MEASure:CURRent? CH1"
scpi_measure_voltage = "MEASure:VOLTage? CH1"
```

The program only sets **current**. Set the supply's voltage limit once (24 V)
so it runs in constant-current mode, and verify communication:

```bash
cd /tmp
sudo -u pidbox /opt/hv-divider-pid/conda-env/bin/python - <<'EOF'
import pyvisa
rm = pyvisa.ResourceManager("@py")
psu = rm.open_resource("TCPIP0::192.168.1.50::INSTR")
print(psu.query("*IDN?"))
psu.write("CH1:CURRent 0")
psu.write("CH1:VOLTage 24")
print(psu.query("MEASure:VOLTage? CH1"), psu.query("MEASure:CURRent? CH1"))
EOF
```

A USB-TMC connection (`USB0::...::INSTR`) also needs a udev rule that gives
the `pidbox` user access to the instrument's USB device.

## B8. Run as a service

After B6 succeeds, start the service:

```bash
sudo systemctl start hv-divider-pid
sudo journalctl -u hv-divider-pid -f      # live log
sudo systemctl status hv-divider-pid
```

Enable automatic start at boot only after a successful supervised run:

```bash
sudo systemctl enable hv-divider-pid
```

Stop (heater is commanded to zero and disabled):

```bash
sudo systemctl stop hv-divider-pid
```

The unit uses `Restart=on-failure`. A latched fault exits with an error, and
systemd starts the controller again 5 s later; it re-enables the heater only
after 5 valid control readings with no over-temperature. Look for
`HEATER FAULT` lines in the journal. If a fault should stay latched until
someone intervenes, change the unit to `Restart=no`.

## B9. After pulling code changes

The service runs the copy in `/opt/hv-divider-pid`, not the Git clone:

```bash
cd ~/hv-divider-temperature-control
git pull
sudo systemctl stop hv-divider-pid
sudo cp standalone_hv_divider_pid.py requirements.txt /opt/hv-divider-pid/
sudo chown pidbox:pidbox \
  /opt/hv-divider-pid/standalone_hv_divider_pid.py \
  /opt/hv-divider-pid/requirements.txt
```

If `hv-divider-pid.service` changed (it did in this revision):

```bash
sudo cp hv-divider-pid.service /etc/systemd/system/hv-divider-pid.service
sudo systemctl daemon-reload
```

If `requirements.txt` changed (it did in this revision):

```bash
sudo chown -R "$USER":"$USER" /opt/hv-divider-pid/conda-env
conda run --prefix /opt/hv-divider-pid/conda-env \
  python -m pip install -r /opt/hv-divider-pid/requirements.txt
sudo chown -R pidbox:pidbox /opt/hv-divider-pid/conda-env
```

`install.sh` never overwrites an existing `/etc/hv-divider-pid/config.toml`.
Merge new settings from the repository `config.toml` by hand
(`diff config.toml /etc/hv-divider-pid/config.toml` shows the differences).

Then start again:

```bash
sudo systemctl start hv-divider-pid
```

## B10. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `PermissionError: ... controller_simulation.csv` | Ran `sudo -u pidbox` from a directory `pidbox` cannot write. `cd /tmp` first. |
| `lgpio.error` / `.lgd-nfy` / `Unable to load any default pin factory` | `lgpio` needs a writable working directory (`cd /tmp`; the service sets `LG_WD=/tmp`). Check `lgpio` is installed in the env. |
| Blinka message about missing `gpiod` at `import board` | `requirements.txt` not reinstalled after this revision; see B9. |
| `ValueError: No I2C device at address: 0x..` | Wiring or address. Compare `i2cdetect -y 1` with the config. |
| `MAX31865 ... fault: RTDINLOW` / `HIGHTHRESH` | Open or shorted RTD lead, or the board's 2/3/4-wire jumpers do not match a 4-wire sensor. |
| `Unknown board pin name ...` | Chip-select pin names must be Blinka names such as `"D5"`. |
| `hardware.visa_resource is required in scpi mode` / VISA timeout | Set `visa_resource`; ping the supply; check the SCPI strings against its manual. |
| Service starts, then restarts every 5 s | A fault is latched at startup. Read `journalctl -u hv-divider-pid`. |

## View Markdown locally

```bash
open README.md HOW_TO_RUN.md docs/HEATER_AND_CURRENT_DRIVER.md   # macOS
```

VS Code previews Markdown, and GitHub renders it automatically.

---

## Revision notes (2026-11-02)

Changes made so the Raspberry Pi instructions run as written:

- `requirements.txt`: added `gpiod>=2.2.2,<3` (Blinka 10.x needs it on the Pi
  and no longer installs it), `lgpio` (gpiozero pin backend, required on Pi 5),
  and `pyusb` (USB-TMC instruments).
- `hv-divider-pid.service`: `Environment=LG_WD=/tmp`, because `lgpio` writes
  FIFOs to its working directory and `/opt` is read-only under
  `ProtectSystem=strict`.
- `config.toml`: `dac_i2c_address` changed from `0x60` to `0x62` (Adafruit
  MCP4725 default).
- `environment.yml`: removed the Anaconda `defaults` channel and the
  machine-specific `prefix:` line.
- `install.sh`: stops on 32-bit OS, installs `libusb-1.0-0`, prints a
  `cd /tmp` test command, and reminds you to reboot.
- Instructions: real clone URL, Miniforge install commands, `cd /tmp` before
  `sudo -u pidbox` runs (the old Pi simulation command failed writing its CSV),
  bus checks, step-by-step commissioning, SCPI example, and the corrected
  `docs/` file name.
