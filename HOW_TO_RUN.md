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
│   └── HV_Divider_Standalone_PID_System_Description.md
└── legacy/
    ├── cryogenic_pid_loop_v2.py
    └── slow_controls_thermal_pid_controller.py
```


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

- PT100 wiring and calibration
- heater resistance
- maximum current
- maximum power
- power-supply command syntax
- output-enable polarity
- independent thermostat
- thermal fuse
- electrical fuse

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

## Troubleshooting interactive Matplotlib widgets

If `%matplotlib widget` reports that `widget` is not a recognized backend,
confirm that `ipympl` is installed:

```bash
conda activate hv-divider-pid
mamba install -c conda-forge ipympl
