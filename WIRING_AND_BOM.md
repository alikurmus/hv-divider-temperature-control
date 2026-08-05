# Proposed Wiring and Bill of Materials

## Functional block diagram

```text
                         OUTSIDE / LOW-VOLTAGE COMPARTMENT

120 VAC
   |
   +--> regulated 24 V DC supply, about 2 A / 50 W
             |
             +--> input fuse --> NC hardware thermostat --> heater-enable relay
             |                                                |
             |                                      current-regulated driver
             |                                   (0-3.3 V command, 0-1.05 A)
             |                                                |
             |                                             INA260
             |                                                |
             |                         twisted heater pair --> heater pad
             |
             +--> 24 V circulation fan (fixed low speed)
             |
             +--> 24-to-5 V DC/DC converter --> Raspberry Pi

Raspberry Pi
   |-- SPI --> MAX31865 --> four-wire PT100 inside enclosure
   |-- I2C --> MCP4725 DAC --> analog command input of current driver
   |-- I2C --> INA260 current/voltage/power monitor
   |-- I2C --> 20x4 panel LCD
   |-- GPIO17 --> hardware current-driver enable / relay
   `-- GPIO27 --> fan enable
```

For the first laboratory prototype, the MCP4725/current-driver combination can
be replaced by a programmable laboratory supply with current programming and
readback over USB or Ethernet. Select `hardware.mode="scpi"` in the software.
This is the quickest way to test the thermal design before building the compact
embedded current driver.

## Recommended ratings

### Heater and heater supply

A practical starting heater is a nominal **24 V, 25 W silicone-rubber heater**.
Its nominal resistance and current are:

- `R = 24^2 / 25 = 23.04 ohm`
- `I = 25 / 24 = 1.042 A`

At the same resistance, approximate currents are:

- 5 W: 0.466 A
- 10 W: 0.659 A
- 15 W: 0.807 A
- 25 W: 1.042 A

The temperature controller will usually use less than the full heater rating;
the extra capacity is for warm-up and changes in laboratory ambient
conditions. Use a 24 V supply rated for at least 1.5 A for the heater alone.
A **24 V, 2 A or larger supply** gives useful margin for the heater, fan, and
conversion losses. The Raspberry Pi may instead use a separate approved 5 V
supply to reduce conducted noise.

The heater must be bonded to an aluminum heat-spreader plate using the heater
manufacturer's recommended pressure-sensitive adhesive or thermal adhesive.
The spreader should heat the circulating air or enclosure wall uniformly and
must not create a local hot spot on a divider board.

### Temperature sensor

Use a **four-wire PT100**, preferably Class A or better, with a mechanically
stable probe or thin-film element. Place the control sensor near the thermal
center of the divider, not directly on the heater or in the fan exhaust. Add a
second independent PT100 near the opposite end to quantify spatial gradients.

A PT100 is about 110.9 ohm at 28 °C. Four-wire sensing removes the resistance of
the lead wires from the measurement. Route the RTD leads separately from the
heater and fan leads. Use shielded cable or two twisted pairs, and terminate the
shield at the controller end only unless the grounding plan specifies
otherwise.

### Temperature readout choice

**Prototype:** MAX31865 breakout, because it is inexpensive and directly
supported by the supplied Python code. It has fine nominal resolution but its
specified total accuracy is not sufficient by itself to certify an absolute
±0.1 °C requirement. Calibrate it near 28 °C and use it for control.

**Acceptance/validation:** use an independent calibrated precision RTD readout,
such as a laboratory PT100 logger or a custom 24-bit RTD front end, to verify
that the physical enclosure actually meets the ripple requirement. The control
sensor and validation sensor should be logged simultaneously.

### Current command and measurement

The MCP4725 provides only a low-power analog voltage. It must feed a separate
current-regulated power stage. Required current-driver characteristics:

- input command: 0 to 3.3 V;
- output current: 0 to at least 1.05 A;
- compliance voltage: at least 24 V;
- monotonic, low-noise analog control;
- output-enable input that defaults OFF;
- current limit and thermal protection;
- adequate heatsinking at the worst operating point.

Do not connect the heater directly to the MCP4725.

The INA260 or supply readback measures heater current and voltage. The display
shows measured `P = V I`. If no readback is available, the program estimates
power using `P = I^2 R_heater`.

### Display

A 20x4 I2C character LCD is adequate and easy to panel mount. It displays:

1. filtered temperature and setpoint;
2. commanded current;
3. measured current and heater power;
4. rolling peak-to-peak ripple and controller status.

A larger TFT can replace it later without changing the PID logic.

## Hardware safety components

The following are not optional for unattended operation:

- input fuse on the 24 V line;
- heater branch fuse sized above normal current but below wire/driver limits;
- normally-closed thermostat mounted at the heater/spreader, wired in series
  with the heater power;
- one-shot thermal fuse at a higher trip temperature;
- normally-off relay or current-driver enable controlled by the Pi;
- physical power switch;
- strain relief and touch-safe terminals;
- wire gauges rated for the maximum current and enclosure temperature;
- fan guard;
- nonflammable mounting materials near the heater;
- independent commissioning thermometer.

Suggested software cutoff for a 28 °C setpoint is 31 °C. The independent
thermostat may be selected around 35-40 °C depending on component limits and
the results of a thermal safety review. The software value is not a substitute
for the hardware cutoff.

## Physical placement in the HV-divider suitcase

- Keep the Raspberry Pi, DAC, current driver, and display electronics outside
  the HV region or in a separately shielded low-voltage compartment.
- Keep the 24 V input and all internal electrical potentials below the agreed
  50 V limit.
- Separate heater/fan wiring from precision divider output wiring.
- Use twisted pairs for heater current and RTD wiring.
- Run the circulation fan continuously at fixed low speed; changing fan speed
  inside the PID loop can introduce another control variable and temperature
  gradients.
- Leave a clear airflow path around the divider boards while respecting HV
  creepage and clearance requirements.
