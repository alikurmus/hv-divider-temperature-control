# Heater and Current-Driver Recommendation

Status: **proposal, 2026-11-02**. To be confirmed by the fixed-power tests and
the electrical-noise qualification in the characterization plan.

## Summary

- **Heater:** a flat resistive DC heater of about **20 Ω total**, bonded to an
  aluminum spreader plate inside the enclosure insulation.
  - For the first thermal tests: two 10 Ω, 25 W aluminum-housed resistors in
    series, bolted to the plate.
  - Final: a polyimide (Kapton) film heater of about 20 Ω, sized after the
    tests.
- **Current driver:** a **linear, voltage-controlled current sink** (op-amp,
  MOSFET, 1 Ω sense resistor) running from the 24 V rail. The existing MCP4725
  DAC commands it, the INA260 reads back current, and a normally-open relay on
  GPIO17 enables it. Nothing switches in the heater path. It works with the
  existing `hardware.mode = "dac"` code without software changes.
- **Prototype shortcut:** until the driver is built, a programmable linear
  bench supply over LAN (`hardware.mode = "scpi"`) is fine for the thermal
  tests.
- **Not recommended:** LED drivers such as Mean Well LDD-H/LDDS-H, and other
  switching or PWM drivers, for the reasons in [Options considered](#options-considered).

## 1. Heat budget: insulate first

The Hammond RMCS190813BK1 body is about 432 × 330 × 222 mm, with roughly
0.6 m² of outer surface. A powder-coated box in still air loses about
8–9 W/(m²·K) by convection plus radiation, so:

| Configuration | Loss conductance G | Power to hold 28 °C in a 20–22 °C room |
|---|---|---|
| Uninsulated, heater on an internal plate | ~2.5–5 W/K | ~15–40 W |
| ~25 mm closed-cell foam (external jacket preferred) | ~0.6 W/K | ~4–5 W |

These are order-of-magnitude estimates. The fixed-power tests measure G and
the time constant directly. The conclusion still holds: **with a ~22 W heater,
the enclosure needs insulation** to get both control margin and a low,
quiet operating current. The 2/5/10 W test plan assumes an insulated box. With
insulation, the time constant is likely several hours.

## 2. Heater

### Choosing the resistance

With a 24 V supply and a linear sink, the sink needs about 1.5–2 V of
headroom. The usable maximum current is roughly `I_max ≈ 22 V / (R_heater + 1 Ω)`:

| R_heater | I_max | Max heater power | Worst-case sink dissipation, 24²/(4·(R+1)) |
|---|---|---|---|
| 10 Ω | 2.0 A | 40 W | 13 W |
| **20 Ω** | **1.05 A** | **22 W** | **6.9 W** |
| 40 Ω | 0.54 A | 11 W | 3.5 W |

At about 20 Ω, the heater reaches the ~25 W characterization scale, the sink
dissipation stays modest, and the expected steady-state operating point is
about 0.4–0.6 A for 3–7 W.

### Phase 1 heater (order now)

Use 2 × 10 Ω, 25 W aluminum-housed wirewound resistors in series (20 Ω), for
example:

- Vishay Dale RH02510R00FE02 (1 %);
- Vishay Dale NH02510R00FE02 (non-inductive);
- Ohmite HS25 10R J (5 %, inexpensive).

Bolt them with thermal compound to opposite ends of a 3–6 mm 6061 aluminum
spreader plate. At 22 W total each dissipates 11 W, well inside its rating on a
plate. They are cheap and robust, have a well-known resistance and are easy to
move during thermal mapping. The case is insulated from the element.

### Phase 2 heater (final)

Use a PSA-backed polyimide (Kapton) film heater of about 20 Ω on the same
spreader for more uniform heat flux. Omega's KHLVA-104/10-P (1"×4", 40 W at
28 V, so R = 28²/40 ≈ 19.6 Ω) runs at ≤ 22 W here. A larger, lower-watt-density
custom heater (Minco, All Flex) can be specified once the tests show where the
heat needs to go. A silicone-rubber heater is the more rugged equivalent.

### Placement and wiring

- Mount the spreader plate on the back wall, along the full length of the
  board stack and parallel to it, never directly against a divider board. With
  the recommended external insulation jacket it can bolt directly to the back
  panel. Include it in the HV clearance review. See
  [`SYSTEM_DESIGN_AND_WIRING.md`](SYSTEM_DESIGN_AND_WIRING.md) for the layout.
- Mount the NC thermostat (opens at 49 °C) and the 72 °C thermal fuse on the
  spreader next to the heater, in series with the heater current.
- Run heater leads as a tightly twisted pair, away from the divider output
  and PT100 cables.

## 3. Current driver: linear low-side current sink

### Schematic (reference design)

```text
+24 V ──F1 3 A T──┬──────────────────────────────► isolated 24→5 V DC-DC ──► Raspberry Pi
                  ├──► U2 L7812CV ──► +12 V (U1 supply only)
                  │
                  └─F2 1.6 A T── TS1 NC 49 °C ── TF1 72 °C ── K1 relay (NO, GPIO17) ── INA260 IN+→IN− ─┐
                                                                                                         │
                                                                                     HEATER ≈ 20 Ω (twisted pair)
                                                                                                         │
 MCP4725 VOUT ──R1 15.0k──┬── A ─────────── U1 (+)                                                   Q1 drain
 (0–3.3 V)                │                 U1 out ──R5 100 Ω──────────────────────────────────── Q1 gate   IRF540N
                    R2 10.0k ═ C1 10 µF     U1 (−) ──R4 1.00k──┬─────────────────────────────── Q1 source
                          │                                     │                                        │
                        AGND               C2 47 nF from U1 out to U1 (−)                         RS 1.00 Ω 5 W
                                                                                                         │
                                          AGND ─────────────────── single star point ─────────────── PGND (24 V return)
```

The circuit holds the voltage across RS equal to the voltage at node A:

```text
I_heater = V_A / RS = 0.4 · V_DAC / 1 Ω      →  0–1.32 A for V_DAC = 0–3.3 V
```

Configuration for this build:

```toml
[control]
heater_resistance_ohm = 20.0        # measure 4-wire
max_power_w = 22.0
max_current_a = 1.05                # keeps ≥1.5 V headroom on Q1

[hardware]
mode = "dac"
dac_i2c_address = 0x62              # Adafruit MCP4725 #935
current_driver_full_scale_a = 1.32  # trim during commissioning (HOW_TO_RUN B6 step 2)
use_ina260 = true
output_enable_gpio = 17             # K1 relay, active high
enable_active_high = true
```

### Parts and values

| Ref | Part | Notes |
|---|---|---|
| U1 | TI TLV2372IP (dual RRIO op-amp, DIP-8, ≤16 V) | Runs from 12 V, so Q1's Vgs stays under 12 V. Tie the unused half as a grounded follower. An LM358 also works. |
| Q1 | Infineon IRF540NPBF (TO-220) | Planar, robust in linear mode. Needs about 4–5 V Vgs at 1 A. |
| RS | Vishay Dale RS0051R000FE12, 1.00 Ω 1 % 5 W | Dissipates ≤1.4 W. Its temperature coefficient only changes the loop gain, which the PID absorbs. |
| R1, R2 | 15.0 kΩ and 10.0 kΩ, 0.1 %, ≤25 ppm/K metal film | Scale the DAC to 0.4×. R2 also pulls the command to 0 if the DAC is unplugged. |
| C1 | 10 µF film or X7R | With R1‖R2 gives a ~60 ms low-pass. It removes DAC and I²C glitches without affecting the thermal loop. |
| R4, C2, R5 | 1.00 kΩ, 47 nF film, 100 Ω | Local loop compensation and gate stopper. Starting values; confirm on a scope that nothing oscillates. |
| U2 | ST L7812CV + 0.33 µF / 0.1 µF | Op-amp supply only (milliamps). |
| Heatsink | Boyd 530002B02500G (TO-220, 20 W at 60 °C rise) | Q1 worst case is 6.9 W at 0.57 A, about a 20–25 K sink rise. Insulate the tab (it is the drain) if mounting to metal. |
| K1 | Adafruit #4409 STEMMA mini relay (2 A at 30 VDC resistive) | Normally open, so the heater is off whenever the Pi is off, booting or crashed. |
| Readback | Adafruit INA260 #4226, high side | Logged `measured_power_w` is 24 V × I (branch power). Heater power is I²R. |

### Where to put it

Put the driver board and the Q1 heatsink **outside the divider enclosure**, in
the controller box with the Pi (see `SYSTEM_DESIGN_AND_WIRING.md`). Steady-state
Q1 dissipation (6–7 W near 0.5 A) is comparable to the heater power. Inside
the box it would be a second, unplanned heater.

The alternative is to mount Q1 and RS on the heater spreader deliberately.
Then all branch power (24 V × I) becomes useful heat. The PID integrator
absorbs the different power-versus-current curve, but `heater_resistance_ohm`
no longer describes the actuator exactly.

### Why it fails safe

| Event | Result |
|---|---|
| Pi off, booting or crashed | GPIO17 is low (pull-down), K1 opens, heater off |
| DAC disconnected | R2 pulls node A to 0 V, I = 0 |
| Software asks for too much current | I ≤ 1.32 A by design and ≤ ~1.14 A by the load; F2 is 1.6 A |
| Q1 fails short (the usual MOSFET failure) | Heater goes to ~25 W. The software over-temperature trip opens K1; TS1 opens at 49 °C; TF1 at 72 °C |
| Over-temperature | Software trip at 31 °C, then TS1 (auto-reset), then TF1 (one-shot) |

### Noise

- Nothing switches in the heater path. Heater-current noise is about the
  op-amp noise divided by RS (tens of nA/√Hz).
- Command updates are at most once per second, slew-limited to 0.05 A/s, with
  0.32 mA DAC steps further smoothed by C1.
- Ripple on the 24 V supply is rejected by the current loop. It appears across
  Q1, not in the heater current.
- The remaining switching sources are the 24 V supply, the 24→5 V converter
  and the Pi. Qualify them per step 6 of the characterization plan.
- Use one star ground: Pi GND, DAC GND and the sink's AGND join the 24 V return
  only at RS. Keep the heater pair and the I²C/SPI wiring away from the divider
  low-voltage output.

### Bench checks before connecting the Pi

1. Power the board from 24 V with a 20 Ω load. Drive node A from a lab source
   at 0.10, 0.50 and 1.00 V. Expect 0.10, 0.50 and 1.00 A (±1–3 %).
2. Scope node A, the gate and the top of RS at 0.1 A and 1 A. There should be
   no oscillation. If there is, increase C2 or R5.
3. Hold 0.57 A for 30 min. Check that the Q1 heatsink temperature is
   acceptable (below about 70 °C).
4. Open K1 and confirm the current goes to zero. Disconnect the DAC and
   confirm the current goes to zero.

## 4. Prototype path: linear bench supply (`mode = "scpi"`)

If the driver is not ready when the enclosure is, a linear programmable supply
on LAN can run the thermal tests. Example: Siglent SPD1305X, 30 V / 5 A,
linear, USB and LAN, SCPI. HOW_TO_RUN.md section B7 has its config strings.
Set its voltage limit to 24 V so it regulates current. Keep the GPIO17 relay in
series as the normally-off hardware enable. The supply is mains-powered, so it
does not meet the final "DC-powered" requirement, but it is outside the
enclosure and is useful later as a reference when qualifying the embedded
driver's noise.

## Options considered

| Option | DC input | Noise in heater path | Fails off by itself? | Pi interface | Verdict |
|---|---|---|---|---|---|
| **Linear sink (this document)** | Yes, 24 V | None (linear) | Yes (K1 + R2) | Existing `dac` mode | **Recommended** |
| Linear programmable bench supply | No (mains) | Low (Siglent spec 350 µVrms) | With K1 | Existing `scpi` mode | Prototype only |
| Mean Well LDDS-H / LDD-H LED driver | Yes, 12–56 V | Buck at 40 kHz–1 MHz, ≤350 mVp-p ripple. PWM dimming at 100 Hz–1 kHz chops the heater current. ≤2.2 µF allowed on the output, so it can't be filtered much | **No: DIM pin open = output ON** | 0–10 V analog (needs a gain stage from the 3.3 V DAC) or PWM; no readback; ±5 % | Not recommended near the divider |
| DC-input programmable buck modules (e.g. RD60xx type) | Yes | Switching | Configurable | Modbus over USB serial: new actuator code needed | Not recommended |
| Wavelength WLD33ND laser-diode driver (WLD3343 replacement) | 5–12 V only | Low | SHD open = enabled | 0–2 V set point | Cannot drive 1 A into 20 Ω |
| Wavelength HTC1500/3000 heater controllers | 5–12 V (30 V by arrangement) | Linear | — | Own PI loop and RTD input | Would replace the Pi PID; different architecture |

If an LED driver is ever tried anyway:

- use analog (0–10 V) dimming, never PWM;
- keep the K1 relay in series;
- keep the INA260 for readback;
- qualify it against the divider output before relying on it.
