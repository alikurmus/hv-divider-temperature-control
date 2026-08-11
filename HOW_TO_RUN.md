# How to Run the Repository with Miniforge/Conda

The repository has two distinct uses:

1. **Laptop mode:** run the thermal simulation and interactive Jupyter notebook.
2. **Raspberry Pi mode:** install and operate the standalone hardware controller.

The workflow below assumes that Miniforge is installed and that `conda` is
available in the shell. `mamba` may be substituted for `conda` in the laptop
environment commands.

Do not run `install.sh` on a Mac. It is intended for Raspberry Pi OS and uses
`apt-get`, `raspi-config`, GPIO, SPI, I²C, and `systemd`.

## Repository contents

```text
.
├── README.md
├── HOW_TO_RUN.md
├── WIRING_AND_BOM.md
├── environment.yml
├── config.toml
├── standalone_hv_divider_pid.py
├── requirements.txt
├── install.sh
├── hv-divider-pid.service
├── notebooks/
│   └── PID_Control_Toy_Simulation.ipynb
├── docs/
│   ├── HV_Divider_Standalone_PID_System_Description.md
│   └── FEEDBACK_RESPONSE.md
└── legacy/
    ├── cryogenic_pid_loop_v2.py
    └── slow_controls_thermal_pid_controller.py
```

The internal meeting notes are intentionally not included.

`README.md` is documentation, not an executable program. GitHub renders it
automatically on the repository front page.

## Create the Conda environment on macOS or Linux

From the repository root:

```bash
conda env create -f environment.yml
conda activate hv-divider-pid
```

If the environment already exists and `environment.yml` changed:

```bash
conda env update -f environment.yml --prune
conda activate hv-divider-pid
```

Confirm the interpreter:

```bash
which python
python --version
```

## Run the standalone thermal simulation

With the environment activated:

```bash
python standalone_hv_divider_pid.py \
  --config config.toml \
  --simulate
```

The controller runs continuously. Stop it with `Ctrl+C`.

Simulation data are written to:

```text
controller_simulation.csv
```

That file is ignored by Git.

## Run the interactive notebook

Register the environment as a Jupyter kernel once:

```bash
conda activate hv-divider-pid
python -m ipykernel install --user \
  --name hv-divider-pid \
  --display-name "HV Divider PID"
```

Start the notebook:

```bash
jupyter lab notebooks/PID_Control_Toy_Simulation.ipynb
```

In JupyterLab, select the **HV Divider PID** kernel if it is not selected
automatically. Run the notebook cells from top to bottom. The `ipywidgets`
controls can then be used to vary the toy-model parameters.

The notebook uses the interactive Matplotlib widget backend. That backend is
provided by the separate `ipympl` package included in `environment.yml`.
Both of the following notebook magics select the same backend:

```python
%matplotlib widget
```

```python
%matplotlib ipympl
```

### Fix a missing Matplotlib widget backend

An error such as:

```text
RuntimeError: 'widget' is not a recognised backend name
```

means that `ipympl` is missing from the Python environment used by the active
Jupyter kernel. Update the existing environment:

```bash
conda activate hv-divider-pid
mamba install -c conda-forge ipympl
```

The equivalent Conda command is:

```bash
conda install -c conda-forge ipympl
```

Then completely restart the notebook kernel. If JupyterLab was launched before
the installation, stop and restart JupyterLab from the same environment:

```bash
conda activate hv-divider-pid
jupyter lab notebooks/PID_Control_Toy_Simulation.ipynb
```

Verify that the active environment contains the backend:

```bash
python -c "import ipympl, ipywidgets, matplotlib; print('ipympl', ipympl.__version__); print('ipywidgets', ipywidgets.__version__); print('matplotlib', matplotlib.__version__)"
```

If JupyterLab and the notebook kernel are deliberately installed in different
Conda environments, install `ipympl` in the kernel environment and
`jupyterlab_widgets` in the environment that launches JupyterLab. The simplest
and recommended setup for this repository is to launch JupyterLab from the
`hv-divider-pid` environment so both parts are in one environment.

## Remove and rebuild the laptop environment

```bash
conda deactivate
conda env remove --name hv-divider-pid
conda env create -f environment.yml
conda activate hv-divider-pid
```

## Install the hardware controller on Raspberry Pi OS

Install Miniforge for the Raspberry Pi architecture first and initialize it for
your shell. Then open a new shell or activate Conda.

Clone the repository:

```bash
git clone https://github.com/YOUR-USERNAME/hv-divider-temperature-control.git
cd hv-divider-temperature-control
```

Review the configuration before enabling hardware:

```bash
nano config.toml
```

Leave this setting during the first test:

```toml
mode = "simulate"
```

Run the installer as your normal Miniforge user. The script invokes `sudo` only
for system-level operations:

```bash
chmod +x install.sh
./install.sh
```

The installer creates a Conda environment at:

```text
/opt/hv-divider-pid/conda-env
```

The service calls that environment's Python directly, so `conda activate` is not
needed by `systemd`.

Run the installed simulation:

```bash
sudo -u pidbox \
  /opt/hv-divider-pid/conda-env/bin/python \
  /opt/hv-divider-pid/standalone_hv_divider_pid.py \
  --config /etc/hv-divider-pid/config.toml \
  --simulate
```

Stop it with `Ctrl+C`.


## New hardware-monitoring options

The first feedback revision adds four PT100 roles, optional humidity monitoring,
and optional fan tachometer monitoring. The default `config.toml` is still in
`simulate` mode. Before changing to real hardware, review these fields:

```toml
control_rtd_cs_pin = "D5"
use_monitor_air_rtd = true
monitor_air_rtd_cs_pin = "D6"
use_ground_board_rtd = true
ground_board_rtd_cs_pin = "D13"
use_spare_rtd = true
spare_rtd_cs_pin = "D19"

use_humidity_sensor = false

# Natural convection is the baseline.
use_fan = false
fan_required = false
fan_tach_gpio = 22
```

Each enabled PT100 requires its own MAX31865 interface. The interfaces share the
SPI bus but use separate chip-select pins.

The control sensor is the only PID input. A control-sensor fault shuts the heater
off. Secondary-sensor faults are warnings, while a valid secondary sensor above
the configured overtemperature limit can still trip the heater.

If `use_humidity_sensor = true`, the Raspberry Pi hardware environment also uses
`adafruit-circuitpython-sht31d`, which is already listed in `requirements.txt`.

The fan is intentionally disabled by default. If testing later shows that a fan
is needed, the program only switches it at fixed speed and can monitor a tach
input; there is no PWM/frequency speed control.

## Select real hardware mode

Edit the installed configuration:

```bash
sudo nano /etc/hv-divider-pid/config.toml
```

For a DAC-controlled external current driver:

```toml
mode = "dac"
```

For a programmable power supply controlled with SCPI:

```toml
mode = "scpi"
```

Before starting hardware mode, verify:

- all enabled PT100/MAX31865 channels and their chip-select pins
- calibration of the control, monitor-air, ground-board, and spare PT100s
- deliberate MAX31865 fault tests (disconnect/open-circuit tests)
- SHT31-D address if humidity monitoring is enabled
- heater resistance
- maximum current
- maximum power
- power-supply command syntax
- output-enable polarity
- if a fan is enabled: fixed-speed wiring, tach GPIO, and required/not-required policy
- independent thermostat
- thermal fuse
- electrical fuse
- rack-enclosure bonding/protective-earth continuity

Start the controller:

```bash
sudo systemctl start hv-divider-pid
```

Enable automatic startup only after successful hardware testing:

```bash
sudo systemctl enable hv-divider-pid
```

View live service output:

```bash
sudo journalctl -u hv-divider-pid -f
```

Check service status:

```bash
sudo systemctl status hv-divider-pid
```

Stop the heater service:

```bash
sudo systemctl stop hv-divider-pid
```

## After changing the Python code

The installed service runs the copy in `/opt/hv-divider-pid`, not directly from
the Git clone. After pulling code changes:

```bash
cd ~/hv-divider-temperature-control
git pull
sudo systemctl stop hv-divider-pid
sudo cp standalone_hv_divider_pid.py requirements.txt /opt/hv-divider-pid/
sudo chown pidbox:pidbox \
  /opt/hv-divider-pid/standalone_hv_divider_pid.py \
  /opt/hv-divider-pid/requirements.txt
sudo systemctl start hv-divider-pid
```

If hardware dependencies changed:

```bash
sudo systemctl stop hv-divider-pid
sudo chown -R "$USER":"$USER" /opt/hv-divider-pid/conda-env
conda run --prefix /opt/hv-divider-pid/conda-env \
  python -m pip install -r /opt/hv-divider-pid/requirements.txt
sudo chown -R pidbox:pidbox /opt/hv-divider-pid/conda-env
sudo systemctl start hv-divider-pid
```

## View Markdown locally

On macOS:

```bash
open README.md
open HOW_TO_RUN.md
open docs/HV_Divider_Standalone_PID_System_Description.md
```

A code editor such as VS Code can also preview Markdown. On GitHub, the files
render automatically.
