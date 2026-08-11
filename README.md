# Standalone HV-Divider Enclosure Temperature Controller

## Purpose

This repository develops a standalone temperature-control system for the HV
voltage-divider enclosure. The current operating target is:

- **setpoint:** 28.0 °C;
- **steady-state target:** less than 0.1 °C rolling peak-to-peak ripple;
- **controller:** continuous PI/PID, not bang-bang;
- **primary actuator:** current-controlled resistive heater;
- **local operation:** Raspberry Pi, independent of external slow controls.

The controller follows the same physics as the notebook example *Heating a
Room with Thermal Loss*:

    C dT/dt = P_heater - G(T - T_ambient)

The PI/PID output is requested **heater power in watts**. Because the heater
hardware is current-controlled, the software converts power to current:

    I_command = sqrt(P_command / R_heater)

Actual heater power is shown as `V*I` when voltage/current readback is
available; otherwise it is estimated as `I^2 R_heater`.

## Current mechanical concept

The earlier suitcase concept has been replaced by a **horizontal 19-inch
rack-mount enclosure** concept. The current preferred candidate is the Hammond
RMC-series **5U solid-panel enclosure RMCS190813BK1** (17 in wide x 13 in deep,
8.73 in overall height). A 6U RMC enclosure remains a fallback if the final HV
clearance, insulation, connector, or mechanical-support layout needs more
height or depth.

The present 5U layout estimate is only a packaging estimate. The previously
used 40 mm HV gap is **not treated in this repository as a validated electrical
safety clearance**. Final creepage/clearance, insulation, feedthrough, and
mechanical spacing require an HV engineering review for the actual voltage,
geometry, materials, environment, and applicable standards.

The Hammond RMC panels are powder coated and the manufacturer notes that the
panels are not automatically grounded to the frame. The final design therefore
needs an explicit enclosure bonding/protective-earth plan; panel-to-panel
continuity must not be assumed.

## Temperature sensing: four PT100 roles

The code now supports four four-wire PT100 channels, each with its own MAX31865
interface and chip-select line:

1. **control_air** — the only sensor used by the PI/PID loop;
2. **monitor_air** — a second air sensor used to independently verify regulation;
3. **ground_board** — attached to the ground board to monitor the temperature
   actually reaching the divider structure;
4. **spare** — an additional monitored PT100 for redundancy/diagnostics.

The monitoring sensors are logged but are not used for automatic control-sensor
failover. If the control sensor fails, the safe behavior is still to turn the
heater off. Automatic failover can be added later only after placement,
calibration, and failure-policy details are agreed.

Every MAX31865 channel now checks the device fault register after a read. A
fault on the control PT100 trips the heater. Faults on monitoring PT100s are
reported as warnings; a healthy monitoring sensor that exceeds the configured
overtemperature threshold can also trip the heater.

## Humidity monitoring

The code supports an optional **SHT31-D relative-humidity sensor** on I2C.
Humidity is monitoring-only: it is logged, displayed, and can raise a warning,
but it does not directly alter the PID output.

The baseline mechanical concept does **not** require a dry-N2 fill or silica-gel
pack. The intent is first to characterize humidity while operating the divider
slightly above room temperature. Whether additional sealing, desiccant, or an
inert-gas fill is needed remains an open design decision based on measurements.

## Fan philosophy

A circulation fan is **not part of the baseline design**. The preferred first
prototype uses natural convection to avoid an additional maintenance item,
failure mode, and possible EMI source.

If thermal mapping shows that forced circulation is necessary, the code
supports an optional fixed-speed fan with tachometer feedback. The fan output is
binary on/off only; this program does not use PWM or frequency-based speed
control. If the fan is configured as required, loss of tachometer pulses trips
the heater.

## Heater drive and electrical readback

The present software supports two paths:

- `scpi`: programmable laboratory/current supply for early thermal testing;
- `dac`: MCP4725 low-voltage analog command into an external current driver.

The **final low-noise current-driver model has not yet been selected**. The
MCP4725 is only a command DAC and cannot drive the heater directly. Selection
of the final driver should follow measured noise/EMI requirements at the divider
output.

A nominal 24 V, 25 W heater remains a reasonable *test-scale* starting point,
but the final heater rating should be set from fixed-power characterization of
the actual rack enclosure rather than assumed in advance.

## Local display

A 20x4 I2C LCD is supported. It cycles between a control page and a diagnostic
page and shows:

- control temperature and setpoint;
- commanded/measured current and power;
- second-air and ground-board temperatures;
- spare PT100 temperature;
- humidity when installed;
- ripple/status;
- fan state when a tachometer-equipped fan is installed;
- a continuously changing heartbeat character.

The display reserves an `SC` field for future external slow-controls
connectivity. At present it shows `N/A` because no external slow-controls
protocol has been selected; standalone local regulation does not depend on that
connection.

## Safety behavior

The heater starts disabled. The controller requires several consecutive valid
control-PT100 readings before enabling it. It turns the current to zero and
disables the hardware output if:

- the control MAX31865/PT100 read fails or reports a hardware fault;
- the control temperature is invalid or exceeds the configured software cutoff;
- a healthy monitor sensor exceeds the cutoff when monitor trips are enabled;
- a required fan reports no tachometer activity;
- the process receives SIGTERM/SIGINT;
- the program raises an unhandled exception;
- the service exits or restarts.

Software is not a substitute for the independent thermostat/thermal cutoff,
thermal fuse, electrical fuse, and properly engineered HV enclosure.

## Recommended physical architecture for the first prototype

- Hammond RMC-series 5U solid enclosure as the current mechanical candidate;
- horizontal divider mounting;
- external regulated 24 V source, sized after heater characterization;
- distributed resistive heater on an aluminum spreader;
- Raspberry Pi Zero 2 W or larger Pi in the low-voltage region;
- four four-wire PT100s + four MAX31865 interfaces;
- optional SHT31-D humidity sensor;
- local 20x4 display;
- current/voltage readback (INA260 or power-supply readback);
- natural convection initially;
- optional fixed-speed tachometer fan only if testing shows it is required;
- independent hardware overtemperature protection and fusing.

See `WIRING_AND_BOM.md` for the current hardware concept and
`docs/FEEDBACK_RESPONSE.md` for what changed after the first design review and
which items are still open.

## Installation

Software setup, Miniforge/Conda instructions, notebook use, simulation, and
Raspberry Pi service installation are in [`HOW_TO_RUN.md`](HOW_TO_RUN.md).

The installed Raspberry Pi locations are:

- program: `/opt/hv-divider-pid/`
- Conda environment: `/opt/hv-divider-pid/conda-env/`
- configuration: `/etc/hv-divider-pid/config.toml`
- CSV log: `/var/log/hv-divider-pid/controller.csv`
- service: `/etc/systemd/system/hv-divider-pid.service`

## Commissioning and tuning

Do not assume the 0.1 °C ripple requirement is guaranteed by software alone.
It depends on insulation, natural-convection gradients, sensor placement,
heater distribution, ambient changes, power-source noise, and the enclosure's
thermal time constants.

Recommended sequence:

1. Install and calibrate all PT100 channels near 28 °C.
2. Log both air sensors and the ground-board sensor with the heater off.
3. Apply several fixed heater powers and map spatial gradients with **no fan**.
4. Measure humidity during warm-up and steady operation.
5. Decide whether natural convection is adequate. Add a fan only if the data
   show unacceptable gradients or time constants.
6. Tune PI with `kd=0` initially.
7. Validate ripple using the independent monitoring PT100/readout.
8. Repeat with the divider measurement electronics active and check for heater,
   fan (if fitted), display, and digital-control EMI.

The example gains in `config.toml` are commissioning placeholders, not final
validated tuning constants.

## Still being decided

The following are intentionally not presented as final choices:

- exact 5U versus 6U enclosure and final rack depth;
- validated 40 kV creepage/clearance and insulation geometry;
- exact divider mounting/support arrangement inside the enclosure;
- final low-noise current-driver or programmable-supply model;
- final heater power/rating after enclosure thermal tests;
- whether a fan is necessary at all;
- whether humidity measurements justify sealing, silica gel, or dry N2;
- exact external slow-controls protocol and therefore the real `SC` connection
  indicator implementation;
- final enclosure bonding/grounding implementation through the powder-coated
  Hammond panels.
