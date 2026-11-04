# TODO: HV-Divider Temperature Control

Created 2026-11-03. Work top to bottom; an item's **Needs** must be done first.
Tick `[x]` when the **Done when** condition is met and write the name of whoever
did it next to the item.

> **Minimal build option:** [`docs/SIMPLEST_DESIGN.md`](docs/SIMPLEST_DESIGN.md)
> is a reduced design: Phase-1 resistors on the enclosure wall, no spreader or
> Kapton, a bench supply as the current source, and two sensors. It has its
> own 10-step checklist. If you choose it, phases 2–4 below shrink to that
> checklist, and D4/D5 and S1 are no longer needed.

The design behind these tasks is in
[`docs/SYSTEM_DESIGN_AND_WIRING.md`](docs/SYSTEM_DESIGN_AND_WIRING.md). Parts are
in [`ORDER_LIST.md`](ORDER_LIST.md). Commissioning commands are in
[`HOW_TO_RUN.md`](HOW_TO_RUN.md), Part B.

---

## Phase 0 — Decisions (before ordering)

- [ ] **D1. Agree on the architecture.** The Pi, the MAX31865 boards and the
  current driver sit in a controller box outside the divider enclosure. Only
  the DC heater pair and four passive PT100 cables enter the enclosure.
  - Done when: agreed at a group meeting (Hamish, Thomas), with a note added
    to the CCA e-gun documentation.
- [ ] **D2. Fix the heater location.** Heaters go on a spreader plate on the
  back wall, along the full length of the board stack. The stack is centered,
  parallel to that wall.
  - Done when: shown in the CAD (M1).
- [ ] **D3. Choose the insulation.** The recommendation is an external foam
  jacket (no foam inside near HV), but an internal lining is possible.
  - Done when: the HV-clearance owner signs off on the choice.
- [ ] **D4. Choose the current-source path.**
  - Recommended: build the linear driver (`mode = "dac"`).
  - Optional: buy a linear LAN bench supply (`mode = "scpi"`) only if thermal
    tests must start before the driver is built.
  - Done when: a yes or no on ORDER_LIST item H1 is recorded.
- [ ] **D5. Choose the box connectors.** Options are LEMO (ask Thomas) or M12
  4-pin A-coded. You need five panel connectors per box: 4 × PT100 and
  1 × heater, with the heater on a different type or keying.
  - Done when: part numbers are added to ORDER_LIST section I.
- [ ] **D6. Assign the sensor roles.**
  - S1 air (PID), S2 air on the far side, S3 ground board, S4 heater plate.
  - If you prefer S4 as a true spare, say so; then the heater-plate sensor is
    dropped.
  - Done when: roles are agreed and written into `config.toml` comments (S2
    item).

## Phase 1 — Ordering

- [ ] **O1. Order ORDER_LIST sections A–G and I.**
  - Done when: all purchase orders are placed and order numbers are recorded
    in ORDER_LIST.
  - Needs: D1, D4, D5.
- [ ] **O2. Check the two "verify" items before ordering:** the Littelfuse
  3 A part number, and the DC voltage rating of the Cantherm DF072S thermal
  fuse.
  - Done when: both are confirmed on the datasheet or replaced.
- [ ] **O3. Check thermostat stock** (Sensata O53GAB120A-105Y, flagged
  discontinued at one distributor). If it is unavailable, choose another NC
  snap-disc that opens at 45–50 °C and is rated ≥ 2 A at 24 VDC.
  - Done when: it is in hand or a substitute is ordered.
- [ ] **O4. Borrow or reserve equipment:**
  - a calibrated reference thermometer (≤ 0.05 °C near 28 °C);
  - a 4-wire ohmmeter (the Fluke DMM);
  - an oscilloscope;
  - an insulation tester (500 V megger).
  - Done when: each has a named source and date.

## Phase 2 — Mechanical design and HV review

- [ ] **M1. Make the CAD layout of the enclosure interior.** Include:
  - the stack, centered and parallel to the back wall;
  - Al board rings or clamps;
  - PEEK or PTFE posts on an Al base plate;
  - the spreader plate on the back wall;
  - sensor positions S1–S4 (SYSTEM_DESIGN §3);
  - the connector panel on the LV/readout side.
  - Done when: the drawing exists with all clearances dimensioned.
  - Needs: D2, D3, D5.
- [ ] **M2. Do the HV clearance and creepage review.** Include the spreader
  plate, heaters, probe sheaths, base plate and posts as grounded or
  low-voltage objects, especially near the HV-in end.
  - Done when: written sign-off, or a list of required changes fed back into
    M1.
  - Needs: M1.
- [ ] **M3. Draw the spreader plate.**
  - Mounting holes for H1 and H2 at ¼ and ¾ of the stack length.
  - Clamp positions for TS1 and TF1 next to the heaters.
  - S4 position between the heaters.
  - Bolt pattern to the back panel. Remove the powder coat under the contact
    area, or use a thermal pad.
  - Done when: the machining drawing is ready.
  - Needs: M1.
- [ ] **M4. Draw the board support parts** (rings, posts, base plate) as
  machining drawings, including the shipping foam blocks.
  - Done when: the drawings are submitted to the shop (Matt or Ali).
  - Needs: M2.
- [ ] **M5. Make the connector-panel cutouts** for DB-HTR, DB-RTD1–4 and the
  PE stud.
  - Done when: the cutouts are machined.
  - Needs: D5, M1.
- [ ] **M6. Make the insulation jacket.** About 25 mm of closed-cell foam on
  all sides, removable, with cutouts for connectors and HV in.
  - Done when: it is fitted and can be removed without tools.
  - Needs: D3.
- [ ] **M7. Lay out the controller box.**
  - Contents: Pi, 4 × MAX31865, DAC, INA260, relay, level shifter, driver
    board with heatsink, DC-DC, F1/F2.
  - LCD on the front.
  - Connectors CB-PWR, CB-HTR, CB-RTD1–4, PE stud, Ethernet.
  - Done when: the panel drawing and internal layout are done.
  - Needs: D5.
- [ ] **M8. Bond the chassis.** Fit straps across all divider-box panels to
  the PE stud.
  - Done when: each panel measures < 0.1 Ω to PE.
  - Needs: M5.

## Phase 3 — Electronics build

- [ ] **E1. Build the linear driver board** (HEATER_AND_CURRENT_DRIVER §3).
  - Done when bench checks 1–4 in that section pass:
    - I = V_A / 1 Ω within 3 %;
    - no oscillation on the scope;
    - heatsink < 70 °C after 30 min at 0.57 A;
    - zero current with the relay open and with the DAC unplugged.
  - Needs: O1.
- [ ] **E2. Wire the Pi header and modules** exactly as SYSTEM_DESIGN §4–5.
  Label every wire with its pin number.
  - Done when: wiring is point-to-point checked against the tables with a
    continuity tester.
  - Needs: O1, M7.
- [ ] **E3. Make the four PT100 cables.** Use Belden 8723: pair A = F+/F−,
  pair B = RTD+/RTD−. Connector pins: 1 F+, 2 RTD+, 3 RTD−, 4 F−. Ground the
  shield at the controller end only.
  - Done when: each cable measures ~110 Ω end-to-end with the sensor attached,
    and 0–2 Ω within each same-end pair.
  - Needs: O1, D5.
- [ ] **E4. Make the heater cable** (2 × 18 AWG twisted; pin 1 HTR+, pin 2
  HTR−).
  - Done when: continuity is OK and there is no short between the pins.
- [ ] **E5. Build the heater assembly** on the spreader: H1, H2 with thermal
  compound, TS1 and TF1 clamped, wired in series to DB-HTR.
  - Done when both hold:
    - ~20 Ω between DB-HTR pins 1–2 (4-wire);
    - > 100 MΩ heater circuit to chassis at 500 V.
  - Needs: M3, O1.
- [ ] **E6. Install sensors S1–S4** in the CAD positions. Secure S3 to the
  ground board only.
  - Done when: each DB-RTD connector reads ~108–112 Ω at room temperature.
  - Needs: M1, E3.
- [ ] **E7. Power-up checks without the Pi running.**
  - 24 V present after F1.
  - 12 V at the driver op-amp.
  - 5 V at the Pi input.
  - Relay open.
  - Heater current 0.
  - Done when: all values are recorded in the logbook.
  - Needs: E1, E2.

## Phase 4 — Software

- [ ] **S1. Add per-sensor over-temperature limits** (required before
  unattended use).
  - New config keys `monitor_air_overtemperature_c`,
    `ground_board_overtemperature_c` and `spare_overtemperature_c`, defaulting
    to `overtemperature_c`.
  - Set `spare_overtemperature_c = 45` for the heater plate.
  - Interim (supervised runs only): `trip_on_monitor_overtemperature = false`.
  - Done when the simulation runs and both of these trip tests pass in
    simulate mode:
    - a fake heater-plate reading of 40 °C does not trip;
    - a reading of 46 °C does trip.
- [ ] **S2. Update `config.toml` comments and values for this layout**
  (SYSTEM_DESIGN §8): roles S1–S4, heater R = measured, full scale 1.32 A,
  `max_current_a = 1.05`, `max_power_w = 22`.
  - Done when: it is committed.
  - Needs: D6.
- [ ] **S3. (Optional) Rename the `spare` role to `heater_plate`** in the code,
  CSV header and LCD for clarity.
  - Done when: it is committed and the simulation runs.
- [ ] **S4. Review and commit the pending repo changes** (HOW_TO_RUN rewrite,
  requirements, service file, environment.yml, install.sh, new docs).
  - Done when: they are merged to `main`.

## Phase 5 — Install and commission (HOW_TO_RUN Part B)

- [ ] **C1. Install the Pi** (B2–B3): 64-bit Raspberry Pi OS, Miniforge, clone,
  `bash install.sh`, reboot.
  - Done when: `install.sh` finishes without errors.
  - Needs: O1, S4.
- [ ] **C2. Check the buses and environment** (B4).
  - Done when both hold:
    - `i2cdetect -y 1` shows 27, 40 and 62;
    - the import check prints `LGPIOFactory`.
  - Needs: C1, E2.
- [ ] **C3. Run the Pi simulation** (B5).
  - Done when: it runs for 2 min and writes `/tmp/controller_simulation.csv`.
  - Needs: C1.
- [ ] **C4. Bring up the sensors with the heater locked at zero** (B6 step 1).
  - Done when all hold:
    - all four sensors read room temperature;
    - unplugging S2, S3 or S4 gives warnings only;
    - unplugging S1 gives `HEATER FAULT` and the program exits.
  - Needs: C2, E6, E7.
- [ ] **C5. Calibrate the PT100s near 28 °C** against the reference
  thermometer. Use a stable bath, or the enclosure at equilibrium during C7.
  - Done when: the slope and offset per channel are in
    `/etc/hv-divider-pid/config.toml` and recorded in the logbook.
  - Needs: C4, O4.
- [ ] **C6. Check the heater path at 1 W fixed** (B6 step 2). Trim
  `current_driver_full_scale_a` until Imeas = Icmd within 1 %.
  - Done when also: the relay closes after 5 samples and opens on `Ctrl+C`.
  - Needs: C4, E5.
- [ ] **C7. Run the fixed-power tests at 2, 5 and 10 W** (B6 step 3), with
  one CSV per run.
  - Done when, for each power, you have recorded:
    - equilibrium S1–S4;
    - G = P/ΔT and τ;
    - the S1–S2 and S1–S3 gradients;
    - the heater-plate temperature.
  - Needs: C6, M6 (jacket on).
- [ ] **C8. Make the gradient decision.**
  - If S1–S3 or S1–S2 is larger than the uniformity requirement, try these in
    order:
    1. move S1 or the stack;
    2. add a second heater zone on the floor, in series on the same driver;
    3. add a fixed-speed fan.
  - Done when: the decision is written down with data.
  - Needs: C7.
- [ ] **C9. Tune the PI** (B6 step 4).
  - Set `power_bias_w` to the steady-state power from C7.
  - Tune P, then I; keep `Kd = 0`.
  - Done when: S1 ripple (peak-to-peak) is < 0.1 °C in every 600 s window for
    12 h, and S3 drift is recorded.
  - Needs: C7, S1 (or interim setting).
- [ ] **C10. Hand over to the service** (B8): `systemctl start`, watch the
  journal for 1 h, then `systemctl enable`. Reboot the Pi once and confirm the
  controller resumes.
  - Done when: it survives the reboot and regulates again.
  - Needs: C9, S1.

## Phase 6 — Qualification (from the meeting notes and project summary)

- [ ] **Q1. Electrical noise.** With the divider readout running, compare:
  - heater off vs on;
  - 0.2 / 0.5 / 1.0 A;
  - Pi and LCD activity;
  - (if H1 was bought) bench supply vs driver.
  - Done when: no measurable modulation or offset, or the culprit is
    identified.
  - Needs: C10.
- [ ] **Q2. Setpoint steps of ±1 °C.** Measure the response and settling time
  (notes A.5).
  - Done when: plots are in the logbook.
  - Needs: C10.
- [ ] **Q3. Ambient disturbance** (notes B). This is optional, since the box
  stays in B037.
  - Done when: the recovery time is recorded, or the test is explicitly
    skipped.
- [ ] **Q4. Divider temperature coefficient** (notes C). Apply a stable
  voltage and step the setpoint (e.g. 27 → 28 → 29 °C), letting it reach
  equilibrium at each step. Consult Caroline (KATRIN method).
  - Done when: you have the tempco value with its uncertainty.
  - Needs: Q1, Q2.
