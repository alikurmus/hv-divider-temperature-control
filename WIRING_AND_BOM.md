# Proposed Wiring and Bill of Materials

This document is the current prototype architecture after the first design
review. Items explicitly marked **TBD** are not yet selected and should not be
interpreted as procurement-ready choices.

## Functional block diagram

```text
                    19-INCH RACK ENCLOSURE / LOW-VOLTAGE REGION

External regulated 24 V DC
          |
          +--> input fuse --> NC hardware thermostat --> heater-enable stage
          |                                                |
          |                                      low-noise current driver
          |                                      (FINAL MODEL: TBD)
          |                                                |
          |                                             INA260
          |                                                |
          |                         twisted heater pair --> heater/spreader
          |
          +--> filtered 5 V converter --> Raspberry Pi
          |                                |
          |                                |-- SPI --> MAX31865 #1 --> PT100 control air
          |                                |-- SPI --> MAX31865 #2 --> PT100 monitor air
          |                                |-- SPI --> MAX31865 #3 --> PT100 ground board
          |                                |-- SPI --> MAX31865 #4 --> PT100 spare
          |                                |-- I2C --> optional SHT31-D humidity sensor
          |                                |-- I2C --> optional MCP4725 command DAC
          |                                |-- I2C --> INA260 current/voltage monitor
          |                                |-- I2C --> 20x4 panel LCD
          |                                `-- GPIO --> heater enable
          |
          `--> OPTIONAL fixed-speed fan --> tach feedback GPIO
                 (baseline prototype omits fan)
```

For the first thermal prototype, the external current-driver path can be
replaced by a programmable laboratory supply with current programming and
readback over USB or Ethernet. Select `hardware.mode="scpi"`. This allows the
thermal design to be characterized before committing to the final embedded
low-noise current driver.

## Mechanical enclosure

### Current candidate

The current preferred enclosure is the **Hammond RMC-series 5U solid-panel
RMCS190813BK1**:

- 19-inch rack-mount format;
- nominal 5U height;
- 17 in body width;
- 13 in depth;
- approximately 8.73 in overall body height;
- approximately 7.81 in inside-height clearance if the optional chassis panel
  is installed.

The divider is currently expected to lie horizontally.

The earlier packaging estimate was approximately:

- 80 mm divider diameter;
- 40 mm nominal gap above;
- 40 mm nominal gap below;
- 10 mm insulation layer top;
- 10 mm insulation layer bottom;
- total approximately 180 mm.

The 5U enclosure appears geometrically plausible from that estimate, but the
**40 mm gap is only a preliminary packaging assumption**. It is not a validated
40 kV safety clearance. Final electrical clearance/creepage and insulation must
be reviewed for the real electrode geometry, materials, environment, altitude,
and applicable safety requirements.

### 6U fallback

If the 5U layout is too tight after the real divider supports, connectors,
insulation, feedthroughs, and bonding hardware are modeled, use a 6U RMC option
instead. Hammond lists 6U solid-panel versions with 13 in and 15 in depths.

### Grounding/bonding warning

The Hammond RMC panels are powder coated. The manufacturer states that the
panels are not automatically grounded to the frame. Therefore:

- do not assume electrical continuity through panel screws alone;
- provide a deliberate chassis/protective-earth bonding scheme;
- verify bond resistance after assembly;
- determine the final grounding topology together with the HV/precision-output
  grounding plan.

The enclosure is not hermetic as supplied. Gaskets/sealant could be added later
if humidity measurements show that sealing is necessary.

## Temperature-sensor architecture

Use **four separate four-wire PT100 channels**, each with its own MAX31865
interface. The MAX31865 boards share SPI clock/data lines but need independent
chip-select lines.

### PT100 roles

| Role | Purpose | PID input? | Failure behavior |
|---|---|---:|---|
| `control_air` | Main air temperature near representative divider volume | Yes | Heater trips |
| `monitor_air` | Independent verification of air regulation/gradient | No | Warning; overtemp can trip |
| `ground_board` | Temperature actually reaching divider ground board | No | Warning; overtemp can trip |
| `spare` | Redundancy/diagnostics | No | Warning; overtemp can trip |

Automatic failover from `control_air` to another PT100 is deliberately **not**
implemented. That policy should only be added once sensor placement and
calibration equivalence have been demonstrated.

### MAX31865 fault handling

The software reads the MAX31865 fault register for every channel. It recognizes
fault flags corresponding to high/low threshold conditions, reference-input
faults, RTD-input faults, and over/undervoltage status. Faults are cleared before
a new transaction and checked after the temperature samples.

A fault on the PID control channel is a heater-off fault. Faults on monitor
channels are logged/displayed as warnings so one failed monitor does not stop a
healthy control loop. Any healthy monitor that sees an overtemperature can be
configured to trip the heater.

### PT100 wiring

Use four-wire PT100s, preferably Class A or better, with mechanically stable
probes or thin-film elements. Route the RTD leads separately from heater and
possible fan wiring. Use shielded cable or two twisted pairs and make the shield
termination part of the final grounding plan.

Calibrate each PT100/readout channel near 28 °C against an independent reference
thermometer. The configuration file has independent slope/offset corrections
for the monitored channels and a separate control-sensor correction.

## Humidity monitoring

An optional **SHT31-D** I2C sensor is supported. It supplies relative humidity
for logging/display and can generate a warning when a configurable RH threshold
is exceeded.

Humidity is not a PID input and does not automatically enable or disable a
desiccant/inert-gas system.

### Baseline humidity strategy

The first prototype should characterize humidity while operating at 28 °C,
slightly above typical room temperature. Do not make dry N2 or silica gel a
required maintenance item unless measurements show they are necessary.

Still to be decided from data:

- no additional humidity control;
- improved sealing/gaskets;
- removable silica-gel pack;
- dry-N2 fill/purge.

## Fan strategy

The baseline design uses **natural convection** and does not require a fan.
This avoids an additional mechanical failure mode, maintenance item, and EMI
source.

If thermal mapping shows that forced circulation is needed, choose a fan with a
separate tachometer/rotation-feedback output. The controller supports:

- fixed on/off operation only;
- tachometer edge monitoring;
- startup grace period;
- heater shutdown if a configured *required* fan stops.

Do not use PWM/frequency speed modulation in this design unless later EMI tests
explicitly show that it is acceptable. If a fan is needed, choose the lowest-EMI
fixed-speed implementation that still provides adequate mixing.

## Heater and heater supply

A **24 V, approximately 25 W resistive heater** remains a practical
characterization scale, not a final requirement. A nominal 24 V / 25 W heater
has approximately:

- `R = 24^2 / 25 = 23.04 ohm`;
- `I = 25 / 24 = 1.042 A` at full rated power.

Approximate current at that resistance:

- 5 W: 0.466 A;
- 10 W: 0.659 A;
- 15 W: 0.807 A;
- 25 W: 1.042 A.

The final required heater power should be selected after fixed-power tests in
the actual rack enclosure with the real insulation and divider mass.

Bond the heater to an aluminum spreader or another deliberately engineered
thermal distribution surface. Do not place a small concentrated heater directly
against a precision divider board.

## Current command and measurement

### Prototype path: programmable supply

A programmable laboratory supply is the preferred first test path because its
current can be commanded and read back while the thermal behavior is measured.
The final SCPI command strings are supply-specific and remain configurable.

### Embedded path: DAC plus current driver

The MCP4725 is only a low-power command DAC. It cannot drive the heater. It must
feed a current-regulated power stage with:

- command input compatible with the DAC range;
- approximately 0-1.05 A output capability for the 25 W test heater;
- normally-off hardware enable;
- appropriate current limiting;
- sufficiently low conducted/radiated noise for the divider measurement.

**The final low-noise current driver is still TBD.** Do not commit the PCB or
mechanical design around a particular driver until its noise has been measured
with the divider readout active.

Use an INA260 or the programmable supply's own readback to monitor current and
voltage. Prefer measured power:

`P_measured = V_measured * I_measured`.

## Display

A 20x4 I2C display is supported. It cycles between two pages.

Main page includes:

- filtered control temperature / setpoint;
- measured or commanded heater current;
- heater power;
- second-air temperature;
- ground-board temperature;
- humidity;
- fan status;
- controller state.

Diagnostic page includes:

- spare PT100;
- rolling ripple;
- warning count;
- reserved external slow-controls connection indicator.

A `| / - \` heartbeat character changes on every display update. This gives a
local indication that the controller process is alive even when the temperature
and current are stable.

The external slow-controls protocol is not selected yet. The display therefore
reports `SC N/A` rather than pretending to know connection status. Once a real
monitoring link is defined, the field can report `OK`/`DOWN`.

## Hardware safety components

The heater circuit should include independent hardware protection in addition
to the Raspberry Pi software:

1. input fuse on the incoming 24 V line;
2. separate heater-branch fuse;
3. normally-closed mechanical thermostat/thermal cutoff near the hottest
   plausible heater location;
4. one-shot thermal fuse above the normal operating range;
5. current driver that defaults off when the command signal or Pi disappears;
6. hardware output-enable line that defaults off;
7. strain relief and appropriate wire gauge;
8. deliberate metal-enclosure bonding/protective-earth scheme;
9. final HV-clearance/creepage review before energizing the divider at high
   voltage.

The software cutoff is an additional layer, not the primary thermal safety
device.

## Current bill of materials

| Item | Quantity | Current choice/status |
|---|---:|---|
| Hammond RMC 5U solid enclosure | 1 | RMCS190813BK1 candidate; 6U fallback |
| Raspberry Pi Zero 2 W or larger | 1 | Proposed |
| Four-wire PT100 | 4 | 2 air + ground board + spare |
| MAX31865 PT100 interface | 4 | One per PT100 |
| SHT31-D humidity sensor | 1 | Optional but recommended for characterization |
| 20x4 I2C LCD | 1 | Proposed |
| Heater | 1 or distributed elements | ~24 V / 25 W characterization scale |
| Aluminum heat spreader | 1 | Geometry TBD |
| Programmable lab supply | 1 | Prototype heater drive, model TBD |
| Low-noise embedded current driver | 1 | **TBD** |
| MCP4725 DAC | 1 | Only if embedded analog driver is used |
| INA260 monitor | 1 | Optional if supply provides adequate V/I readback |
| Tachometer-output fan | 0 or 1 | **Not baseline; only if thermal data require it** |
| Independent thermostat/cutoff | 1 | Required |
| Thermal fuse | 1 | Required |
| Electrical fuses | as required | Required |
| 24 V external supply | 1 | Final current rating after heater choice |
| 24-to-5 V converter or separate Pi supply | 1 | Noise testing required |

## Still being decided

- 5U versus 6U and final enclosure depth;
- validated HV clearances/creepage and insulation geometry;
- exact divider supports and feedthrough positions;
- final enclosure sealing level;
- whether natural convection is sufficient;
- whether humidity requires desiccant or dry N2;
- final low-noise current driver;
- final heater wattage;
- exact chassis/protective-earth bonding implementation;
- external slow-controls protocol and connection-status implementation.
