# Standalone HV-Divider Enclosure Temperature Controller

## Purpose

This package stabilizes the inside of the HV-divider enclosure at **28.0 °C**.
The performance target is **less than 0.1 °C rolling peak-to-peak ripple** after
the box reaches equilibrium. It is independent of Dripline/slow controls and
runs as a Linux service on a Raspberry Pi.

The controller follows the same physics as the notebook example *Heating a
Room with Thermal Loss*:

    C dT/dt = P_heater - G(T - T_ambient)

The PI/PID output is requested **heater power in watts**. Because the heater
hardware is current-controlled, the software converts power to current:

    I_command = sqrt(P_command / R_heater)

The actual power shown on the display is read as `V*I` when current/voltage
readback is available. Otherwise it is estimated as `I^2 R_heater`.

## Recommended physical architecture (based on discussion on July 31st)

Keep all digital/controller electronics in a shielded low-voltage compartment
on the exterior or at one end of the suitcase, away from the HV divider and its
low-level output wiring.

- External regulated 24 V DC source, approximately 2 A / 50 W.
- 24 V, approximately 25 W silicone-rubber resistive heater bonded to an
  aluminum heat-spreader plate. Do not place the heater directly against the
  precision divider boards.
- Low-noise analog current driver, 0 to approximately 1.05 A, with a 0 to 3.3 V
  command input and a hardware enable input. Alternative: a programmable DC
  supply with current programming/readback over USB or Ethernet.
- Four-wire PT100 RTD near the thermally representative center of the divider.
- MAX31865 RTD interface for prototype/control use. Calibrate near 28 °C.
- INA260 high-side current/voltage/power monitor, or the programmable supply's
  own readback.
- Raspberry Pi Zero 2 W or larger Raspberry Pi.
- 20x4 I2C character LCD mounted on the top panel.
- Small 24 V brushless fan run continuously at fixed speed for internal mixing.
- Normally-off heater relay/current-driver enable.
- Independent normally-closed thermostat and thermal fuse in series with the
  heater, plus an appropriately rated fuse on the 24 V input.

A 5 W supply should not be selected without a thermal test. The box may consume
only a few watts at equilibrium, but a 25 W heater provides warm-up and ambient
change headroom. The software limits it to the configured maximum.

## PT100 readout

A PT100 is nominally 100 ohm at 0 °C. Near 28 °C it is approximately 110.9 ohm.
The MAX31865 applies an excitation, measures the RTD resistance relative to a
precision reference resistor, digitizes the ratio, and converts it to
temperature. Four-wire wiring removes lead-wire resistance from the reading.

The code asks the Adafruit MAX31865 library for `sensor.temperature`, takes
several samples, rejects non-finite values, and uses their median. It then
applies a configurable calibration slope and offset. The old cryogenic 13-17
ohm calibration polynomial is intentionally not used for this room-temperature
PT100 application.

## Display

The four display rows are:

1. filtered temperature and 28 °C setpoint;
2. commanded heater current;
3. measured current and power;
4. rolling temperature ripple and state (`START`, `RAMP`, `WAIT`, `STABLE`, or
   `RIPPLE`).

## Safety behavior

The heater starts disabled. The controller requires several consecutive valid
PT100 readings before enabling it. It turns the current to zero and disables
the hardware output if:

- the PT100 read fails or returns an invalid value;
- temperature exceeds the configured software cutoff;
- the process receives SIGTERM/SIGINT;
- the program raises an unhandled exception;
- the service exits or restarts.

Software is not a substitute for the independent thermostat, thermal fuse, and
fuse in the physical heater circuit.

## Installation location

Install the software on the Raspberry Pi at:

- program: `/opt/hv-divider-pid/`
- configuration: `/etc/hv-divider-pid/config.toml`
- CSV log: `/var/log/hv-divider-pid/controller.csv`
- service: `/etc/systemd/system/hv-divider-pid.service`

The Pi and current driver should be outside the HV volume or in a separated,
shielded low-voltage compartment. Only the PT100, heater, and low-noise fan need
to be inside the temperature-controlled volume.

## First installation

From this package directory on Raspberry Pi OS:

```bash
chmod +x install.sh
./install.sh
```

First test the controller without hardware:

```bash
cd /opt/hv-divider-pid
sudo -u pidbox .venv/bin/python standalone_hv_divider_pid.py \
  --config /etc/hv-divider-pid/config.toml --simulate
```

Then edit `/etc/hv-divider-pid/config.toml`, select either `mode="dac"` or
`mode="scpi"`, verify all current limits and the heater resistance, and start:

```bash
sudo systemctl start hv-divider-pid
sudo journalctl -u hv-divider-pid -f
```

## Commissioning and tuning

Do not promise the 0.1 °C ripple from software alone. It depends on insulation,
air mixing, sensor placement, heater distribution, power-supply noise, and the
thermal time constants.

1. Install the heater, fan, and at least one PT100. A second independent PT100
   is strongly recommended to measure spatial gradients.
2. With PID disabled, apply fixed powers such as 2 W, 5 W, and 10 W. Record the
   temperature rise, settling time, and spatial gradients.
3. Determine the heater resistance at operating temperature from measured V/I.
4. Calibrate the control PT100 near 28 °C against a traceable thermometer.
5. Start with `kd=0`, low `kp`, and low `ki`. Increase `kp` until warm-up is
   acceptably fast without oscillation. Increase `ki` only enough to remove the
   remaining steady-state error.
6. Evaluate rolling peak-to-peak ripple only after the full enclosure has
   reached thermal equilibrium. Use the independent calibrated sensor for the
   acceptance measurement.

The example gains in `config.toml` are deliberately conservative placeholders;
they are not guaranteed tuning constants for the final enclosure.
