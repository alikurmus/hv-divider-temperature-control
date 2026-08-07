# Standalone PID Temperature-Control System for the HV Divider Box

## 1. Purpose

This system is intended to stabilize the inside of the high-voltage-divider enclosure at:

- **Temperature setpoint:** 28.0 °C
- **Target ripple:** less than 0.1 °C peak-to-peak during steady operation
- **Control type:** continuous PI/PID control, not bang-bang
- **Actuator:** current-driven resistive heater
- **Temperature sensor:** four-wire PT100
- **Controller:** standalone Raspberry Pi-based system
- **Display:** local display of temperature, current, power, and ripple
- **Slow controls:** optional, not required for operation

The design is based conceptually on the “Heating a Room With Thermal Loss” PID example. The box continuously loses heat to the surrounding laboratory, while the controller adds only enough heater power to maintain the requested temperature.

---

## 2. Recommended System Architecture

The complete system consists of:

1. A PT100 resistance thermometer inside the box
2. A precision PT100 interface board
3. A Raspberry Pi running the control code
4. A controllable heater-current source
5. A 24 V resistive heater
6. A small circulation fan
7. A panel-mounted display
8. Current and voltage readback
9. Independent overtemperature protection
10. An external stabilized 24 V DC power supply

The basic control path is:

```text
PT100
  ↓
PT100 interface / ADC
  ↓
Raspberry Pi
  ↓
PI/PID calculation
  ↓
Desired heater power
  ↓
Desired heater current
  ↓
Current driver or programmable power supply
  ↓
Resistive heater
  ↓
Heat added to box
```

The circulation fan should run continuously at a fixed low speed. It should not be used as a second PID actuator.

---

## 3. Controller Is Computing Power

The original cryogenic-cavity code commands current directly. That interface can be retained, but the thermal controller should think in terms of heater power.

For a resistive heater:

\begin{equation}
P = I^2 R
\end{equation}

where:

- $P$ is heater power in watts
- $I$ is heater current in amperes
- $R$ is heater resistance in ohms

The controller first calculates the desired heater power:

\begin{equation}
P_{\rm command}
= K_P e + K_I \int e\,dt - K_D \frac{dT}{dt}
\end{equation}

where:

\begin{equation}
e = T_{\rm set} - T_{\rm measured}.
\end{equation}

The desired current is then:

\begin{equation}
I_{\rm command}
= \sqrt{\frac{P_{\rm command}}{R_{\rm heater}}}.
\end{equation}

This makes the controller more physically meaningful because heater current does not produce heat linearly. Doubling current produces four times as much resistive heating.

---

## 4. Recommended Controller Type

The first implementation should use a **PI controller**:

- proportional term enabled
- integral term enabled
- derivative term initially set to zero

For a slow thermal system, derivative control often adds sensitivity to sensor noise without providing much benefit.

The controller should include:

- integral anti-windup
- current and power limits
- current slew-rate limiting
- temperature filtering
- overtemperature shutdown
- sensor-failure shutdown
- startup validation
- data logging
- rolling ripple calculation

Derivative control can be enabled later if testing shows that it improves settling without increasing noise.

---

## 5. Heater and Power Calculation

A reasonable starting heater is:

- **Nominal voltage:** 24 V
- **Nominal power:** 25 W
- **Type:** silicone-rubber resistive heater
- **Approximate resistance:** 23.04 Ω

The resistance is:

\begin{equation}
R = \frac{V^2}{P}
=
\frac{24^2}{25}
=
23.04\ \Omega.
\end{equation}

The full-power current is:

\begin{equation}
I = \frac{P}{V}
=
\frac{25}{24}
=
1.04\ \mathrm{A}.
\end{equation}

Example operating points are:

| Heater power | Current | Approximate heater voltage |
|---:|---:|---:|
| 2 W | 0.295 A | 6.79 V |
| 5 W | 0.466 A | 10.7 V |
| 10 W | 0.659 A | 15.2 V |
| 15 W | 0.807 A | 18.6 V |
| 25 W | 1.042 A | 24.0 V |

The heater will probably require only a few watts once the box reaches equilibrium. However, a heater and supply rated for approximately 25 W provide useful warm-up and disturbance-recovery headroom.

A 5 W supply is therefore not recommended as the main supply. It may regulate the box after warm-up, but it may be unable to bring the box to temperature quickly or compensate for a cool laboratory.

---

## 6. Recommended Power Supplies

### 6.1 Main 24 V supply

Use an external regulated supply with approximately:

- 24 V DC output
- at least 2 A capacity
- low output ripple
- good line and load regulation
- appropriate safety certification
- external location if possible

A 24 V, 2–2.5 A supply provides enough capacity for:

- the heater
- fan
- current-driver losses
- auxiliary electronics
- operating margin

The meeting notes specifically favored bringing 24 V into the suitcase and keeping internal voltages below 50 V.

### 6.2 Raspberry Pi supply

Use either:

- a separate approved 5 V Raspberry Pi supply, or
- a well-filtered 24 V-to-5 V DC/DC converter

During early commissioning, a separate Pi supply is preferable because it makes noise debugging easier.

### 6.3 Heater current control

The Raspberry Pi cannot directly drive the heater. It must command one of the following:

#### Option A: Programmable power supply

A laboratory or embedded programmable supply that supports:

- current programming
- current readback
- voltage readback
- remote output enable
- USB, serial, or Ethernet SCPI control

#### Option B: Analog current driver

A standalone current-regulator circuit that accepts a low-voltage command, such as 0–3.3 V, and produces approximately 0–1.05 A.

A DAC such as an MCP4725 may generate the analog command signal, but the DAC cannot directly supply heater current.

---

## 7. Measuring Actual Heater Power

The actual power should be calculated from measured voltage and current:

\begin{equation}
P_{\rm measured}=V_{\rm measured}I_{\rm measured}.
\end{equation}

If voltage readback is unavailable, power can be estimated using:

\begin{equation}
P_{\rm estimated}=I_{\rm measured}^2R_{\rm heater}.
\end{equation}

The display and log should preferably show:

- commanded current
- measured current
- measured heater voltage
- measured heater power

A current/voltage monitor such as an INA260 may be used when an external analog current driver is selected. A programmable power supply may provide these values directly.

---

## 8. PT100 Temperature Measurement

### 8.1 Description of a PT100

A PT100 is a platinum resistance thermometer with a nominal resistance of:

\begin{equation}
R(0^\circ\mathrm{C})=100\ \Omega.
\end{equation}

Its resistance increases with temperature.

Near room temperature, the standard relation is approximately:

\begin{equation}
R(T)=R_0(1+AT+BT^2),
\end{equation}

where:

- $R_0=100\ \Omega$
- $A=3.9083\times10^{-3}\ ^\circ\mathrm{C}^{-1}$
- $B=-5.775\times10^{-7}\ ^\circ\mathrm{C}^{-2}$

At 28 °C, the PT100 resistance is approximately:

\begin{equation}
R(28^\circ\mathrm{C})\approx110.90\ \Omega.
\end{equation}

### 8.2 How the temperature is measured

The readout electronics:

1. Send a small excitation current through the PT100
2. Measure the resulting voltage
3. Determine the PT100 resistance
4. Convert resistance to temperature
5. Report sensor faults such as open or short circuits

### 8.3 Four-wire measurement

A four-wire PT100 uses:

- two wires for excitation current
- two wires for voltage sensing

This greatly reduces error from cable resistance.

Because the stability requirement is less than 0.1 °C, a two-wire sensor is not recommended. Cable resistance and connector changes can easily create errors comparable to the entire allowed ripple.

### 8.4 PT100 interface

A MAX31865-based PT100 interface is a practical starting point. The code configures it for:

- PT100 nominal resistance: 100 Ω
- reference resistor: typically 430 Ω
- four-wire mode
- SPI connection to the Raspberry Pi

The controller should take several readings per cycle, reject invalid readings, and use the median to reduce occasional spikes.

### 8.5 Filtering

The controller uses both:

- raw temperature for logging and diagnostics
- filtered temperature for PID control

A low-pass filter helps prevent current changes caused by individual noisy readings.

Filtering must not be so strong that it hides real thermal changes.

### 8.6 Calibration

The PT100 channel should be calibrated near 28 °C using an independent reference thermometer.

The software should support:

\begin{equation}
T_{\rm corrected}
=
mT_{\rm measured}+b,
\end{equation}

where:

- $m$ is a calibration slope
- $b$ is a calibration offset

For validating the 0.1 °C requirement, use a separate precision thermometer or calibrated RTD readout.

---

## 9. Sensor Placement

At least one PT100 is required for feedback, but two or three are preferable during commissioning.

Recommended locations:

1. Control sensor near the divider assembly
2. Independent validation sensor at the opposite side of the box
3. Optional heater-spreader sensor for safety monitoring

The control PT100 should:

- measure the representative air or divider temperature
- not touch the heater directly
- not be directly in the heater’s hottest airflow
- be mechanically fixed
- be shielded from strong electrical pickup
- be positioned away from high-voltage conductors

The validation sensor determines whether the box is truly uniform and whether the control sensor is representative.

---

## 10. Heater and Fan Placement

The heater should be bonded to an aluminum spreader plate rather than heating a small local spot.

A recommended arrangement is:

```text
Heater pad
   ↓
Aluminum heat-spreader plate
   ↓
Low-speed circulation fan
   ↓
Mixed warm air through box
```

The divider should not receive direct concentrated hot airflow.

The fan should:

- run continuously
- operate at fixed low speed
- have low vibration
- be kept away from precision low-voltage output wiring
- be tested for electromagnetic interference

The enclosure should have external insulation, but sufficient internal clearance must remain for airflow and high-voltage spacing.

---

## 11. Display

A panel-mounted display can show:

```text
Temperature:  28.003 C
Setpoint:     28.000 C
Command:       0.466 A
Measured:      0.464 A
Heater power:  4.98 W
Ripple:        0.043 C p-p
State:         STABLE
```

A 20×4 I²C character display is a simple option.

A small graphical display can also be used, but a character display is easier to integrate and debug.

The display is local only. The controller does not need slow controls or a network connection to operate.

---

## 12. Control Loop Sequence

Each control cycle performs the following steps:

1. Read the PT100 several times
2. Reject invalid readings
3. Compute the median temperature
4. Apply calibration
5. Apply low-pass filtering
6. Verify the temperature is within plausible limits
7. Check the independent overtemperature limit
8. Compute temperature error
9. Update the integral term
10. Calculate desired heater power
11. Clamp desired power to safe limits
12. Convert power to current
13. Apply current slew-rate limiting
14. Send current command to the heater driver
15. Read back actual current and voltage
16. Calculate actual power
17. Update rolling ripple calculation
18. Update the display
19. Append values to the CSV log
20. Sleep until the next control cycle

A one-second control period is reasonable. The thermal plant is slow, but the faster sampling helps with filtering, display updates, fault detection, and logging.

---

## 13. Ripple Calculation

The target is less than 0.1 °C ripple.

The controller calculates rolling peak-to-peak ripple:

\begin{equation}
\Delta T_{\rm pp}
=
T_{\rm max}-T_{\rm min}
\end{equation}

over a configurable time window, such as 10 minutes.

The system should report `STABLE` only when:

- the temperature is close to 28 °C
- enough data have accumulated
- the rolling peak-to-peak ripple is below 0.1 °C

The final requirement should be verified over a longer interval, such as one or more hours, using the independent thermometer.

---

## 14. Safety Requirements

Software shutdown alone is not sufficient.

The complete system should include:

### Software safety

- maximum allowed temperature
- minimum plausible temperature
- maximum plausible temperature
- sensor-fault detection
- current limit
- power limit
- communication-failure shutdown
- exception-triggered heater shutdown
- shutdown on program termination
- startup validation before enabling heat

### Hardware safety

- normally closed mechanical thermostat
- one-shot thermal fuse
- heater-branch electrical fuse
- main 24 V input fuse
- default-off current driver
- hardware output-enable line
- safe wire gauge
- strain relief
- guarded fan
- flame-resistant wiring and insulation where appropriate

The software default overtemperature threshold may be set near 31 °C for an initial 28 °C target, but the final value should be agreed upon based on the divider and enclosure materials.

The mechanical thermostat should be mounted near the heater or hottest expected location.

---

## 15. Recommended Bill of Materials

| Component | Recommended specification |
|---|---|
| Controller | Raspberry Pi Zero 2 W, Pi 3, Pi 4, or equivalent |
| Temperature sensor | Four-wire PT100, Class A or better |
| PT100 interface | MAX31865 breakout configured for PT100 |
| Validation thermometer | Calibrated precision RTD readout |
| Heater | 24 V, approximately 25 W silicone heater |
| Heat spreader | Aluminum plate |
| Main supply | Regulated 24 V, at least 2 A |
| Heater driver | SCPI programmable supply or analog current source |
| DAC, if required | MCP4725 or equivalent |
| Current/voltage monitor | INA260 or equivalent |
| Fan | Small 24 V low-vibration brushless fan |
| Display | 20×4 I²C LCD |
| Hardware thermostat | Normally closed thermostat |
| Thermal fuse | One-shot cutoff above permitted temperature |
| Electrical protection | Input and heater-branch fuses |
| Wiring | Twisted heater pair and shielded PT100 cable |
| Connectors | Locking low-voltage connectors |
| Insulation | External rigid foam suitable for enclosure |
| Mounting | Standoffs, thermal adhesive, strain reliefs, fan guard |
| Controller enclosure | Shielded low-voltage compartment |

---

## 16. Electrical Separation and Noise Control

The HV-divider output is a precision low-level signal, so the thermal-control system must be tested for interference.

Recommended practices:

- Keep the heater controller outside the HV region
- Use a separate shielded low-voltage compartment
- Keep heater wiring away from divider-output wiring
- Twist heater supply and return wires
- Use shielded PT100 wiring
- Avoid PWM heater control if it creates measurable pickup
- Prefer continuous analog current control
- Run the fan at fixed speed
- Test fan noise and heater-current noise separately
- Use one controlled chassis-ground connection
- Avoid unintended ground loops
- Keep digital display wiring away from precision output connectors
- Measure the divider output with heater off and on during commissioning

The notes also emphasize thermal-equilibrium concerns in low-voltage connectors. Symmetric materials and similar connector temperatures are important for reducing thermoelectric offsets.

---

## 17. Mechanical Installation

Install the Raspberry Pi, display, PT100 interface, and current-control electronics:

- outside the main HV volume, or
- in a physically separated low-voltage compartment

Install inside the controlled space:

- PT100 sensor
- optional validation PT100
- heater and spreader
- circulation fan
- mechanical thermostat
- thermal fuse

The large suitcase-sized enclosure is preferable because it provides more room for:

- HV clearance
- airflow
- thermal insulation
- separated electronics
- mechanical support
- shipping protection

---

## 18. Software Installation

Recommended file locations:

```text
/opt/hv-divider-pid/
    standalone_hv_divider_pid.py
    requirements.txt

/etc/hv-divider-pid/
    config.toml

/var/log/hv-divider-pid/
    controller.csv

/etc/systemd/system/
    hv-divider-pid.service
```

Install the package:

```bash
chmod +x install.sh
sudo ./install.sh
```

Run in simulation mode first:

```bash
cd /opt/hv-divider-pid

sudo -u pidbox .venv/bin/python \
    standalone_hv_divider_pid.py \
    --config /etc/hv-divider-pid/config.toml \
    --simulate
```

After wiring and validation, choose the hardware mode in `config.toml`.

For a programmable supply:

```toml
mode = "scpi"
```

For a DAC-controlled current driver:

```toml
mode = "dac"
```

Start the service:

```bash
sudo systemctl start hv-divider-pid
sudo systemctl enable hv-divider-pid
```

View live logs:

```bash
sudo journalctl -u hv-divider-pid -f
```

---

## 19. Commissioning Procedure

### Stage 1: Electronics-only checkout

- Leave the heater disconnected
- Confirm PT100 readings
- Compare against a reference thermometer
- Test the display
- Test CSV logging
- Test simulated current commands
- Test output-enable behavior
- Disconnect the PT100 and verify shutdown
- Trigger an overtemperature simulation and verify shutdown

### Stage 2: Low-power heater test

- Connect the heater
- Apply a low fixed-current command
- Measure heater resistance
- Confirm current and voltage readback
- Confirm calculated power
- Check wiring and connector temperatures
- Confirm hardware thermostat operation

### Stage 3: Thermal characterization

Run several fixed-power tests, for example:

- 2 W
- 5 W
- 10 W

Record:

- ambient temperature
- steady-state box temperature
- warm-up time
- temperature gradients
- heater-spreader temperature
- fan effect

This determines the approximate heat-loss coefficient of the box.

### Stage 4: PI tuning

Begin with:

- $K_D=0$
- small $K_P$
- small $K_I$
- conservative current limit

Increase $K_P$ until the system responds adequately but does not oscillate strongly.

Then increase $K_I$ until steady-state offset is removed.

If overshoot occurs:

- reduce $K_I$
- reduce $K_P$
- decrease current slew rate
- improve fan mixing
- reduce maximum warm-up power near the setpoint

### Stage 5: Stability validation

Operate for several hours and verify:

- mean temperature near 28 °C
- ripple below 0.1 °C peak-to-peak
- no persistent oscillation
- no strong dependence on fan cycles
- no coupling into divider output
- no local hot spots
- no software or communication faults

Repeat the test for realistic laboratory ambient-temperature changes.

---

## 20. Important Limitations

The software alone cannot guarantee less than 0.1 °C ripple.

Performance also depends on:

- enclosure insulation
- heater placement
- heat-spreader design
- fan mixing
- PT100 quality
- PT100 placement
- ADC/readout noise
- current-driver stability
- ambient laboratory variations
- electrical interference
- final PI tuning

The included gains should be treated as commissioning values, not final validated values.

---

## 21. Final Recommended Standalone System

A practical implementation is:

```text
24 V / 2.5 A external stabilized supply
                 │
                 ├── 24 V circulation fan
                 │
                 ├── heater current driver
                 │        │
                 │        └── 24 V / 25 W heater
                 │
                 └── filtered 5 V converter or separate Pi supply
                          │
                    Raspberry Pi
                          │
          ┌───────────────┼────────────────┐
          │               │                │
       MAX31865         I²C LCD         INA260
          │                                │
      4-wire PT100                  heater V/I readback
```

This configuration provides:

- standalone operation
- continuous current control
- local temperature readout
- local current and power readout
- automatic startup
- CSV logging
- independent shutdown logic
- optional later integration with slow controls
- commercially available components
- enough heater capacity for warm-up and thermal disturbances

The correct initial hardware scale is therefore closer to:

> **24 V, approximately 25 W heater + 24 V, 2–2.5 A supply + four-wire PT100 + MAX31865 + Raspberry Pi + continuous current driver + fan + display + independent thermal safety devices**

rather than a 5 W power supply and PT100 alone.
