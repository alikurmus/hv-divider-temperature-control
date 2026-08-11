# Standalone PID Temperature-Control System for the HV Divider

## 1. Scope and operating target

The temperature-control subsystem is intended to keep the high-voltage divider
near a fixed operating temperature while remaining independent of external slow
controls.

Current requirements:

- nominal setpoint: **28.0 °C**;
- steady-state target: **less than 0.1 °C peak-to-peak ripple** over the selected
  evaluation window;
- continuous PI/PID heater regulation, not bang-bang control;
- local display and logging;
- safe heater-off behavior on control-sensor and overtemperature faults;
- optional future readout by external slow controls without making slow controls
  necessary for regulation.

The controller is conceptually based on the notebook example *Heating a Room
With Thermal Loss*. The enclosure is modeled as a thermal mass exchanging heat
with its surroundings:

$$
C\frac{dT}{dt}=P_{\mathrm{heater}}-G(T-T_{\mathrm{ambient}}).
$$

The software controller requests heater power, while the physical actuator is
current controlled:

$$
P_{\mathrm{command}}=K_P e+K_I\int e\,dt-K_D\frac{dT}{dt},
$$

with

$$
e=T_{\mathrm{set}}-T_{\mathrm{control}},
$$

and

$$
I_{\mathrm{command}}=\sqrt{\frac{P_{\mathrm{command}}}{R_{\mathrm{heater}}}}.
$$

The first hardware tuning should use PI control with $K_D=0$.

---

## 2. Mechanical concept after the first design review

### 2.1 Rack mount rather than suitcase

The current mechanical concept is a horizontal divider mounted in a standard
19-inch aluminum rack enclosure rather than a standalone suitcase.

The present preferred candidate is the Hammond RMC-series **5U unvented
RMCS190813BK1**. Hammond lists the body as approximately:

- 8.73 in overall height;
- 17.00 in body width;
- 13.00 in depth;
- 5U rack format;
- 7.81 in inside-height clearance when the optional chassis panel is installed.

Manufacturer series information:

- <https://www.hammfg.com/electronics/small-case/rack-mount/rmc>
- <https://www.hammfg.com/part/RMCS190813BK1>

A 6U model remains a fallback if the final insulation, supports, feedthroughs,
connectors, or HV clearance require more room. Hammond lists 6U versions with
13 in and 15 in depths.

### 2.2 Preliminary vertical packaging estimate

The current rough vertical estimate is:

- divider diameter: approximately 80 mm;
- preliminary gap above: approximately 40 mm;
- preliminary gap below: approximately 40 mm;
- insulation: approximately 10 mm top + 10 mm bottom;
- total: approximately 180 mm.

The 5U enclosure therefore appears plausible as a packaging candidate.

However, **the 40 mm value is not treated here as a validated 40 kV electrical
safety clearance**. Final clearance and creepage must be determined from the
actual geometry, materials, environment, altitude, insulation system, and
applicable electrical-safety requirements. The mechanical CAD should reserve
room conservatively until that review is complete.

### 2.3 Enclosure bonding

The Hammond RMC enclosure is powder coated. Hammond explicitly notes that the
panels are not automatically grounded to the frame. Therefore the final design
must include a deliberate enclosure bonding/protective-earth scheme. Electrical
continuity through the assembly screws alone must not be assumed.

### 2.4 Sealing

The RMC enclosure is not hermetic as supplied. It could potentially be modified
with gaskets/sealant, but sealing is not a baseline requirement until humidity
measurements show that it is useful.

---

## 3. Temperature-sensor architecture

### 3.1 Four PT100 channels

The first feedback review recommended more temperature information and sensor
redundancy. The updated design therefore uses four four-wire PT100 channels:

1. **control air PT100** — PI/PID feedback sensor;
2. **monitor air PT100** — independent air-temperature monitor;
3. **ground-board PT100** — attached to the divider ground board;
4. **spare PT100** — additional monitor/redundancy channel.

Each PT100 uses its own MAX31865 interface. The four interfaces can share SPI
clock, MOSI, and MISO, while each has an independent chip-select pin.

The example configuration uses:

- `D5`: control air;
- `D6`: monitor air;
- `D13`: ground board;
- `D19`: spare.

These are software defaults and must be checked against the final Raspberry Pi
wiring before construction.

### 3.2 One control sensor, several monitor sensors

Only `control_air` is fed into the PI/PID algorithm. This follows the common
approach of regulating from one well-characterized sensor while using additional
sensors to verify gradients and the actual structure temperature.

The monitor sensors are deliberately **not** used for automatic failover. If
the control PT100 fails, the heater turns off. Automatic failover would require
confidence that another sensor has sufficiently equivalent placement,
calibration, and thermal response, and that policy has not yet been established.

### 3.3 PT100 calibration

All channels should be compared against an independent reference thermometer
near 28 °C. The code supports slope/offset corrections:

$$
T_{\mathrm{corrected}}=mT_{\mathrm{measured}}+b.
$$

The control PT100 has its own calibration parameters. Each monitor PT100 has
separate calibration parameters in `config.toml`.

---

## 4. MAX31865 fault handling

The MAX31865 interface provides a fault register in addition to the temperature
readout. The updated code clears previous faults before a read and checks the
fault state after the temperature samples.

The software recognizes the six fault flags exposed by the CircuitPython
MAX31865 library:

- `HIGHTHRESH`;
- `LOWTHRESH`;
- `REFINLOW`;
- `REFINHIGH`;
- `RTDINLOW`;
- `OVUV`.

Fault policy:

- **control-air MAX31865 fault:** immediate heater shutdown;
- **monitor-air / ground-board / spare fault:** warning and logging, while the
  healthy control loop continues;
- **valid monitor temperature above the configured overtemperature limit:**
  heater shutdown when `trip_on_monitor_overtemperature=true`.

This makes use of the MAX31865 diagnostics without allowing a failed secondary
monitor to unnecessarily disable an otherwise healthy controller.

---

## 5. Humidity monitoring

### 5.1 Why measure humidity

Humidity can influence surface leakage on a high-resistance divider, so it is
useful to record it even if no active humidity-control system is ultimately
required.

The software now supports an optional **SHT31-D** sensor over I2C. It reports
relative humidity for:

- CSV logging;
- panel display;
- warning generation above a configurable threshold.

Humidity is **not** a heater-control input.

### 5.2 Baseline strategy

The first prototype should not require dry nitrogen, silica gel, or a hermetic
enclosure. The divider will operate above room temperature, so the first step is
to measure the actual RH behavior inside the rack enclosure.

Possible later responses if humidity is unexpectedly high or unstable:

- improve gasket/seal performance;
- use a serviceable silica-gel pack;
- add a dry-N2 fill/purge;
- leave the enclosure as-is if measurements show no problem.

The data should decide whether the maintenance burden of desiccant or gas is
justified.

---

## 6. Fan strategy

### 6.1 Natural convection is the baseline

The first prototype should be evaluated without a fan. This avoids:

- an additional mechanical failure point;
- maintenance;
- vibration;
- possible electromagnetic interference;
- the need to verify fan rotation.

The enclosure should be thermally mapped with the divider horizontal and the
heater distributed appropriately. If natural convection is sufficient to meet
spatial-uniformity and response-time requirements, no fan is necessary.

### 6.2 Optional fan path

If measurements show that forced mixing is required, the code supports a
fixed-speed fan with tachometer feedback.

The fan implementation is intentionally simple:

- full on/off output only;
- no PWM speed control;
- no frequency modulation;
- tachometer edge counting over a configurable time window;
- optional heater trip when a required fan stops.

A tachometer-equipped low-EMI fan should be selected only after it is clear that
a fan is necessary.

---

## 7. Heater and power scale

A 24 V / approximately 25 W resistive heater remains a useful characterization
scale. For a nominal 24 V, 25 W heater:

$$
R=\frac{24^2}{25}=23.04\ \Omega,
$$

and full-power current is approximately:

$$
I=\frac{25}{24}=1.042\ \mathrm{A}.
$$

Approximate operating points at 23.04 Ω:

| Heater power | Current | Approx. voltage |
|---:|---:|---:|
| 2 W | 0.295 A | 6.79 V |
| 5 W | 0.466 A | 10.7 V |
| 10 W | 0.659 A | 15.2 V |
| 15 W | 0.807 A | 18.6 V |
| 25 W | 1.042 A | 24.0 V |

This is **not yet the final heater specification**. Fixed-power tests in the
actual 5U/6U enclosure should determine how much power is required to hold 28 °C
under realistic ambient conditions.

The heater should distribute heat through a spreader or another intentionally
designed thermal surface instead of creating a local hot spot near a divider
board.

---

## 8. Current control and readback

### 8.1 Prototype

For early thermal tests, a programmable laboratory supply is the simplest path.
The code supports generic SCPI current programming and current/voltage readback.
Supply-specific commands remain configurable.

### 8.2 Embedded final system

The code also supports an MCP4725 DAC that provides a low-voltage command to an
external current driver.

The DAC is **not** a heater driver. The final current-driver power stage needs:

- output capability appropriate to the selected heater;
- stable continuous analog control;
- normally-off hardware enable;
- current limiting;
- sufficiently low conducted and radiated noise for the precision divider
  readout.

### 8.3 Still open: low-noise driver

No final low-noise current-driver model has been selected. This should remain
open until the required current range and acceptable noise are quantified with
the divider readout. A driver that looks electrically convenient should not be
accepted before an EMI/noise test.

### 8.4 Power measurement

Prefer measured power:

$$
P_{\mathrm{measured}}=V_{\mathrm{measured}}I_{\mathrm{measured}}.
$$

If direct voltage readback is not available, estimate:

$$
P_{\mathrm{estimated}}=I^2R_{\mathrm{heater}}.
$$

The code supports INA260 readback for the embedded path or direct readback from
a programmable supply.

---

## 9. Display and local status

The current 20x4 LCD implementation alternates between two pages.

### Main page

Displays:

- filtered control temperature and setpoint;
- measured or commanded heater current;
- measured/estimated power;
- second-air temperature;
- ground-board temperature;
- humidity;
- fan status;
- controller state.

### Diagnostic page

Displays:

- spare PT100 temperature;
- rolling ripple;
- warning count;
- external slow-controls status field.

### Heartbeat

The final character of the top row cycles through:

```text
| / - \
```

This changes every display update, providing a visible heartbeat even when all
physical values have stabilized.

### External slow-controls indicator

The controller is intentionally standalone, and no external slow-controls
protocol has yet been selected. Therefore the current display reports `SC N/A`.
It does **not** report a false connectivity state. Once the interface is defined,
this field can become a real `SC OK` / `SC DOWN` indicator.

Faults replace the normal display with a heater-off fault screen.

---

## 10. Logging

The CSV log now records:

- control-air PT100;
- filtered control temperature;
- monitor-air PT100;
- ground-board PT100;
- spare PT100;
- relative humidity;
- setpoint and PID terms;
- commanded current/power;
- measured current, voltage, and power;
- rolling ripple;
- fan rotation status;
- MAX31865/auxiliary sensor faults;
- warning summary;
- controller state.

This gives enough information to diagnose temperature gradients, humidity,
heater behavior, and sensor failures during commissioning.

---

## 11. Control-loop sequence

Each cycle performs:

1. read the control PT100;
2. check its MAX31865 fault state;
3. read monitor-air, ground-board, and spare PT100s;
4. record monitor-channel faults without automatically stopping regulation;
5. read humidity if enabled;
6. validate control temperature and all healthy monitor temperatures;
7. trip on overtemperature according to policy;
8. check air-sensor disagreement and humidity warning thresholds;
9. check fan tachometer if a fan is installed;
10. compute PI/PID power from the control-air temperature only;
11. convert requested power to current;
12. apply power/current limits and current slew limiting;
13. command the current source;
14. read back current/voltage/power;
15. update rolling ripple;
16. update LCD/console heartbeat and diagnostics;
17. append a CSV row;
18. sleep until the next cycle.

---

## 12. Ripple definition

The reported ripple is rolling peak-to-peak control-air temperature:

$$
\Delta T_{\mathrm{pp}}=T_{\max}-T_{\min}
$$

within the configured window, currently 600 s.

The 0.1 °C performance requirement should ultimately be validated with the
independent monitor/reference measurement as well as the control channel. A low
control-sensor ripple is insufficient if large spatial gradients exist across
the divider.

---

## 13. Safety layers

### Software

- control-sensor MAX31865 fault -> heater off;
- invalid control temperature -> heater off;
- software overtemperature -> heater off;
- healthy monitor overtemperature -> heater off when enabled;
- required-fan tach failure -> heater off;
- output power/current limits;
- current slew limit;
- startup sensor validation;
- shutdown on exception/process exit;
- warnings for monitor faults, humidity, and sensor disagreement.

### Independent hardware

The heater circuit should still have:

- 24 V input fuse;
- heater-branch fuse;
- normally-closed thermostat/thermal cutoff;
- one-shot thermal fuse;
- current driver that defaults off;
- hardware enable that defaults off;
- appropriate conductor sizing and strain relief;
- proper rack-enclosure bonding/protective earth;
- completed HV insulation/clearance review.

No Raspberry Pi program should be the sole protection against heater runaway.

---

## 14. Recommended prototype bill of materials

| Item | Quantity | Status |
|---|---:|---|
| Hammond RMCS190813BK1 5U enclosure | 1 | Current candidate |
| 6U RMC enclosure | alternative | Fallback if layout requires |
| Raspberry Pi Zero 2 W or larger | 1 | Proposed |
| Four-wire PT100 | 4 | Proposed |
| MAX31865 | 4 | One per PT100 |
| SHT31-D | 1 | Optional/recommended for characterization |
| 20x4 I2C LCD | 1 | Proposed |
| Resistive heater | 1/distributed | Final power TBD |
| Aluminum thermal spreader | 1 | Geometry TBD |
| Programmable lab supply | 1 | Prototype current source, model TBD |
| Embedded low-noise current driver | 1 | **TBD** |
| MCP4725 | 1 | Only for analog embedded driver |
| INA260 | 1 | Optional if supply readback sufficient |
| Fixed-speed tach fan | 0 or 1 | Not baseline |
| Independent thermostat/cutoff | 1 | Required |
| Thermal fuse | 1 | Required |
| Electrical fuses | as needed | Required |
| External 24 V supply | 1 | Final rating after heater choice |
| 5 V Pi supply/DC-DC | 1 | Noise characterization required |

---

## 15. Commissioning plan

### Stage 1: sensor bench test

- connect all four PT100/MAX31865 channels;
- deliberately open/short each sensor one at a time and confirm its software
  fault reporting;
- verify that control-sensor faults shut the heater path down;
- verify monitor-sensor faults generate warnings rather than false control
  values;
- calibrate all channels near 28 °C;
- test the SHT31-D if installed;
- verify LCD heartbeat and fault screen.

### Stage 2: enclosure thermal mapping without fan

- mount the divider horizontally in the candidate enclosure;
- place both air PT100s at separated representative locations;
- attach the board PT100;
- leave the fan out;
- apply fixed heater powers such as 2, 5, and 10 W;
- record equilibrium temperatures and warm-up time;
- compare air-to-air and air-to-board gradients;
- log relative humidity.

### Stage 3: decide whether a fan is needed

Only if natural convection produces unacceptable gradients or response time:

- install a fixed-speed low-EMI fan with tach output;
- confirm tach feedback and heater-trip behavior;
- compare gradients with and without the fan;
- measure divider-output EMI with the fan active.

### Stage 4: PI tuning

- start with $K_D=0$;
- use conservative $K_P$ and $K_I$;
- raise $K_P$ until response is useful without strong oscillation;
- increase $K_I$ only enough to eliminate steady offset;
- re-check ripple and gradients after full thermal equilibrium.

### Stage 5: electrical-noise qualification

With the precision divider readout active:

- compare heater off versus steady current;
- compare different heater currents;
- compare programmable supply versus candidate embedded current driver;
- test display activity;
- test Raspberry Pi digital activity;
- if a fan is fitted, test fan on/off;
- verify no unacceptable modulation or offset enters the precision measurement.

### Stage 6: long stability run

Operate for several hours while recording:

- all four PT100s;
- humidity;
- heater current/voltage/power;
- ambient temperature if available;
- warnings/faults;
- divider output.

The final acceptance should address both temporal ripple and spatial temperature
differences.

---

## 16. Still being decided

The following are open and deliberately left configurable or optional:

1. 5U versus 6U enclosure and final depth;
2. final validated HV clearance/creepage and insulation system;
3. divider support and feedthrough geometry;
4. enclosure sealing/gasket requirements;
5. whether natural convection is sufficient;
6. whether humidity requires silica gel, sealing, or dry N2;
7. final low-noise current driver;
8. final heater wattage and physical heater geometry;
9. exact chassis/protective-earth bonding implementation;
10. external slow-controls protocol and actual connectivity heartbeat;
11. whether automatic PT100 control-sensor failover is ever desirable.

These are engineering decisions to be made from mechanical layout, thermal
measurements, and precision-noise testing rather than assumptions in software.