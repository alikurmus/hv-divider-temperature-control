# Response to First Repository Feedback

This document records how the first round of collaborator feedback was folded
into the temperature-control repository. It is intended to distinguish
implemented software changes from hardware choices that remain open.

## Implemented changes

### 1. Multiple PT100 sensors

The controller now supports four PT100/MAX31865 channels:

- `control_air`: PID feedback;
- `monitor_air`: independent air monitor;
- `ground_board`: divider ground-board monitor;
- `spare`: additional redundancy/diagnostics.

Only `control_air` is used by the PI/PID algorithm. The other sensors are logged
and displayed. Automatic failover is intentionally not implemented yet.

### 2. MAX31865 fault status

The code now uses the MAX31865 fault register. It clears old faults before a
transaction and checks the six fault flags after reading.

Policy:

- control-sensor fault -> heater off;
- monitor-sensor fault -> warning/log entry;
- healthy monitor sensor over software overtemperature threshold -> heater off
  when `trip_on_monitor_overtemperature=true`.

### 3. Humidity monitoring

Optional SHT31-D support was added. Relative humidity is logged and shown on the
LCD. A warning threshold can be configured.

Humidity is monitoring-only. It does not directly change PID power.

### 4. Fan changed from required to optional

The previous architecture assumed a continuously running fan. That assumption
was removed.

The default is now:

```toml
use_fan = false
```

The first prototype should test natural convection. If a fan later proves
necessary, the code supports fixed-speed on/off operation and tachometer
feedback. It does not use PWM or frequency-based speed control.

If the fan is configured as required, missing tach activity shuts the heater
off.

### 5. Display heartbeat and diagnostics

The LCD now cycles between a control page and a diagnostic page. A `| / - \\`
character changes every update to provide a visible heartbeat even when all
measurements are stable.

The display also includes:

- second-air temperature;
- ground-board temperature;
- spare PT100;
- humidity;
- fan status;
- warning count;
- reserved slow-controls status field.

The slow-controls field currently reports `N/A` rather than pretending that a
connection exists.

### 6. Rack-mount enclosure replaces suitcase assumption

Documentation now uses a horizontal 19-inch rack enclosure as the baseline
mechanical concept.

Current preferred candidate:

- Hammond RMC series;
- 5U solid-panel `RMCS190813BK1`;
- approximately 8.73 in overall height;
- 17 in body width;
- 13 in depth;
- approximately 7.81 in internal height clearance with the optional chassis
  installed.

A 6U RMC enclosure remains the fallback if final mechanical or HV spacing needs
more room.

Hammond source:

- <https://www.hammfg.com/electronics/small-case/rack-mount/rmc>
- <https://www.hammfg.com/part/RMCS190813BK1>

### 7. Powder-coat grounding issue added to design requirements

Hammond notes that the powder-coated panels are not automatically grounded to
the frame. The documentation now explicitly requires a deliberate
chassis/protective-earth bonding scheme and verification of continuity.

### 8. The 40 mm HV gap is no longer presented as an engineering requirement

The 40 mm number is retained only as a preliminary packaging assumption used in
the 180 mm vertical stack estimate. It is explicitly labeled as **not a
validated 40 kV safety clearance**. Final clearance/creepage and insulation must
be reviewed for the actual geometry and applicable requirements.

### 9. More complete logging

The CSV now includes:

- all four PT100 temperatures;
- relative humidity;
- fan state;
- MAX31865/monitor sensor faults;
- warning text;
- existing PID, current, voltage, power, and ripple values.

### 10. Hardware dependency update

`adafruit-circuitpython-sht31d` was added to `requirements.txt`. The Raspberry
Pi installer already installs that file into the dedicated Conda environment,
so no installer redesign was required.

## Still being decided

### Low-noise current driver

No final driver has been selected. The repository still supports:

- a programmable SCPI supply for initial testing;
- an MCP4725 command DAC for a later analog current-driver stage.

The final driver should be chosen after the acceptable conducted/radiated noise
at the divider output and the final heater current range are known.

### Fan versus natural convection

Natural convection is now the baseline. A fan is retained only as a software
and wiring option. Thermal mapping of the horizontal divider in the rack
housing should decide whether it is needed.

### Humidity-control method

The code can measure humidity, but no maintenance-intensive control strategy is
required by default. The following remain possibilities if data justify them:

- no additional humidity control;
- gaskets/sealant;
- silica gel;
- dry-N2 fill/purge.

### 5U versus 6U enclosure

The 5U unit is the preferred candidate, but the final choice depends on the
mechanical CAD, real divider supports, connectors/feedthroughs, insulation, and
validated HV clearance.

### External slow-controls link

The local PID is intentionally standalone. No protocol or endpoint has been
specified for external slow controls, so the display cannot yet show a real
connection state. The LCD reserves the field for later implementation.

### Automatic control-sensor failover

The added PT100s provide redundancy and diagnostics, but failover from the
control sensor is not enabled. A failover policy requires agreement on sensor
placement, calibration equivalence, and acceptable behavior after a sensor
fault.

### Final heater and supply sizing

The 24 V / 25 W heater remains a characterization scale rather than a final
procurement requirement. Fixed-power tests in the real enclosure should set the
final power rating.
