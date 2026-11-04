# Order List — PID Temperature Control

Prepared 2026-11-02 for the design in
[`docs/HEATER_AND_CURRENT_DRIVER.md`](docs/HEATER_AND_CURRENT_DRIVER.md).

- Prices are approximate USD from vendor pages seen on that date. Re-check
  stock before ordering.
- "Spare" quantities cover one-shot or easily damaged parts.
- Items marked **verify** were not fully confirmed on a vendor page.
- For the minimal build, use the shorter parts list in
  [`docs/SIMPLEST_DESIGN.md`](docs/SIMPLEST_DESIGN.md) instead (≈ $540–950,
  depending on whether you buy the bench supply).

## A. Controller

| # | Item | Qty | Part number / vendor | ~Unit $ | Notes |
|---|---|---:|---|---:|---|
| A1 | Raspberry Pi 4 Model B, 2 GB | 1 | Adafruit [#4292](https://www.adafruit.com/product/4292) or other authorized reseller | 67.50 list | Pi 5 2 GB (~$77.50) also works, but usually needs a fan. Pi 4 runs passively. |
| A2 | Passive aluminum heatsink case for Pi 4 | 1 | e.g. Flirc Pi 4 case | ~15 | Avoid fans near the divider. |
| A3 | microSD, 32 GB, A1/A2, high-endurance | 2 | any major brand | ~10 | Second card for a backup image. |
| A4 | Isolated 24→5 V DC-DC, 6 A | 1 | Mean Well **DDR-30G-5** ([TRC](https://www.trcelectronics.com/products/mean-well-ddr-30g-5)) | 35.36 | 9–36 V in, DIN rail. Non-isolated alternative: Pololu D36V50F5 ($39.95). |
| A5 | Perma-Proto HAT or screw-terminal HAT for the Pi | 1 | Adafruit / similar | ~10 | Clean SPI/I²C/GPIO wiring. |
| A6 | Pi 4 USB-C 5 V 3 A supply | 1 | Raspberry Pi official 15 W | ~8 | Bring-up before the 24 V wiring exists. |

## B. Temperature sensing

| # | Item | Qty | Part number / vendor | ~Unit $ | Notes |
|---|---|---:|---|---:|---|
| B1 | MAX31865 PT100 amplifier (430 Ω ref) | 5 | Adafruit [#3328](https://www.adafruit.com/product/3328) | 14.95 | 4 + 1 spare. Set jumpers for 4-wire. |
| B2 | PT100, **4-wire, Class A**, 1/8"×3" sheath, ~40" leads (air sensors) | 3 | Evolution Sensors [P4A-TBSX-125-PX-3-PFXX-40-STWL](https://evosensors.com/products/4-wire-pt100-rtd-probe-3-inches-long-x-1-8-diameter-stainless-steel-sheath-with-40-inches-of-pfa-lead-wire), or Omega [PR-10H-4-100-1/8-6](https://www.dwyeromega.com/en-us/rtd-probe-with-insulated-wire-and-shrink-tube-support/p/PR-10) | 65 / ~46+ | S1 air (control), S2 air (far side), plus 1 spare. In Omega PR-10 part numbers the digit after the series is the wire count (4 = 4-wire). |
| B3 | PT100, **4-wire, Class A**, self-adhesive surface sensor | 2 | Omega [SA1-RTD-4W](https://rspsupply.com/p-791063-omega-sa1-rtd-4w-surface-rtd-class-a-4-wire.aspx) | 132–159 | S3 ground board, S4 heater plate. For S4, a 4-wire thin-film element epoxied to the plate is a cheaper alternative. |
| B4 | Shielded 2-pair cable, 22 AWG | 15 m | Belden 8723 | ~2/m | One pair for excitation, one for sense, per PT100. |
| B5 | Humidity sensor SHT31-D (optional) | 1 | Adafruit [#2857](https://www.adafruit.com/product/2857) | 13.95 | Recommended for characterization. |
| B6 | Calibrated reference thermometer (≤0.05 °C near 28 °C) | 1 | borrow a lab standard | — | Needed for PT100 calibration. |

## C. Command, readback, enable, display

| # | Item | Qty | Part number / vendor | ~Unit $ | Notes |
|---|---|---:|---|---:|---|
| C1 | MCP4725 12-bit DAC | 2 | Adafruit [#935](https://www.adafruit.com/product/935) | 4.95 | I²C address **0x62** (config updated). |
| C2 | INA260 current/voltage/power monitor | 2 | Adafruit [#4226](https://www.adafruit.com/product/4226) | 9.95 | 0x40. |
| C3 | Relay, normally open, 3 V-logic input | 2 | Adafruit [#4409](https://www.adafruit.com/product/4409) | 6.95 | Contacts 2 A at 30 VDC (resistive). Heater enable on GPIO17. |
| C4 | STEMMA QT / Qwiic cables, 100 mm | 6 | Adafruit [#4210](https://www.adafruit.com/product/4210) | 0.95 | |
| C5 | 20x4 LCD with PCF8574 I²C backpack | 1 | SunFounder [I2C LCD2004](https://www.sunfounder.com/products/i2c-lcd2004-module) | 14.99 | Runs on 5 V at address 0x27 (0x3F with the PCF8574A chip). Not Adafruit #292, which uses an MCP23008; the code expects a PCF8574. |
| C6 | Bidirectional I²C level shifter (3.3 V ↔ 5 V) | 1 | SparkFun BOB-12009, or Adafruit #757 (was out of stock) | ~4 | For the 5 V LCD backpack. |

## D. Linear current driver (reference design)

| # | Item | Qty | Part number | ~Unit $ | Notes |
|---|---|---:|---|---:|---|
| D1 | Dual RRIO op-amp, DIP-8, ≤16 V | 3 | TI **TLV2372IP** | ~2 | U1 |
| D2 | N-MOSFET, TO-220, 100 V | 3 | Infineon **IRF540NPBF** | ~1.5 | Q1 + spares |
| D3 | Sense resistor 1.00 Ω, 1 %, 5 W | 2 | Vishay Dale **RS0051R000FE12** | ~2 | RS |
| D4 | TO-220 heatsink, 20 W at 60 °C rise | 2 | Boyd **530002B02500G** | ~3 | Q1 dissipates ≤7 W. |
| D5 | TO-220 insulating pad + shoulder washer | 4 | any (Sil-Pad type) | ~1 | The Q1 tab is the drain. |
| D6 | 12 V linear regulator | 2 | ST **L7812CV** | ~0.7 | U2, op-amp supply. |
| D7 | Precision resistors, 0.1 %, ≤25 ppm/K | 4 each | 15.0 kΩ (R1), 10.0 kΩ (R2) | ~1 | DAC scaling 0.4×. |
| D8 | Passives kit | 1 | 1.00 kΩ, 100 Ω, 10 µF film/X7R, 47 nF film, 0.33 µF, 0.1 µF ×4, 100 µF/50 V | ~10 | |
| D9 | Protoboard, 5.08 mm screw terminals, small vented aluminum box | 1 set | any | ~25 | Mount outside the insulated volume. |

## E. Heater and thermal hardware

| # | Item | Qty | Part number / vendor | ~Unit $ | Notes |
|---|---|---:|---|---:|---|
| E1 | **Phase-1 heater:** 10 Ω, 25 W aluminum-housed resistor | 4 | Vishay Dale **RH02510R00FE02** (1 %) or **NH02510R00FE02** (non-inductive); budget: Ohmite **HS25 10R J** ([DigiKey HS2510RJ-ND](https://www.digikey.com/en/products/detail/ohmite/HS25%2010R%20J/HS2510RJ-ND/5307681)) | 6–27 | 2 in series = 20 Ω, plus 2 spares. **Verify** price. |
| E2 | **Phase-2 heater:** Kapton film heater, PSA, 1"×4", 40 W at 28 V (≈19.6 Ω) | 1 | Omega **KHLVA-104/10-P** ([Newark 32AH9514](https://www.newark.com/c/automation-process-control/industrial-heaters/flexible-heaters?brand=omega&watt-density=10w-in-)) | 80.05 | Order now, or after the fixed-power tests if a larger custom heater is preferred. |
| E3 | 6061 aluminum plate, 1/8"–1/4" thick, cut to the enclosure floor or rear wall | 1 | McMaster-Carr / local | ~40 | Heat spreader. |
| E4 | Thermal compound | 1 | e.g. Wakefield 120 or similar | ~10 | Under E1 resistors. |
| E5 | Closed-cell foam insulation, ~25 mm, flame-retardant | ~0.8 m² | local / McMaster | ~50 | **External jacket** around the enclosure (recommended, so there is no foam near HV). Decision D3 in TODO.md. |
| E6 | Hammond RMCS190813BK1 5U enclosure | 1 | Hammond / distributor | — | Only if not yet ordered. |
| E7 | Insulating rod for board-support posts | ~1 m | PEEK or PTFE rod, McMaster-Carr | ~40–150 | Size per M4 drawings. Avoid fiber-filled laminates with exposed edges. |
| E8 | Aluminum for board rings and base plate | per drawing | 6061 plate or bar | — | Per M4 drawings. |

## F. Safety

| # | Item | Qty | Part number / vendor | ~Unit $ | Notes |
|---|---|---:|---|---:|---|
| F1 | Snap-disc thermostat, SPST-NC, opens 49 °C (120 °F) | 2 | Sensata/Airpax **O53GAB120A-105Y** ([DigiKey 723-1225-ND](https://www.digikey.com/en/products/detail/sensata-technologies/053GAB120A-105Y/723-1225-ND/1631992)) | ~42 | 3 A at 24 VDC. One distributor lists it as discontinued; check stock. Avoid TO-220 Airpax 67L parts (0.5 A DC). |
| F2 | Thermal fuse, 72 °C, one-shot | 4 | Cantherm SDF **DF072S** ([DigiKey 317-1124-ND](https://www.digikey.co.uk/en/products/detail/SDF%20DF072S/317-1124-ND/1014753)) | ~1 | 10 A rated. **Verify** the DC voltage rating. |
| F3 | Fuse 5×20 mm time-lag, 1.6 A (heater branch) | 5 | Littelfuse **021801.6MXP** | ~0.5 | |
| F4 | Fuse 5×20 mm time-lag, 3 A (24 V input) | 5 | Littelfuse 218 series, 3 A (0218003.MXP, **verify**) | ~0.5 | |
| F5 | 5×20 mm fuse holders (panel or inline) | 2 | any | ~3 | |

## G. Power and wiring

| # | Item | Qty | Part number / vendor | ~Unit $ | Notes |
|---|---|---:|---|---:|---|
| G1 | 24 V DC supply, ≥60 W | 1 | Mean Well **GST90A24-P1M** (24 V 3.75 A; [Jameco](https://www.jameco.com/z/GST90A24-P1M-MEAN-WELL-24-Volt-3750mA-90-Watt-3-Wire-Regulated-Switching-Desktop-Power-Adapter-2-5mm-Plug-Level-VI_2223494.html)) | 30.80 | Needs an IEC C13 cord. DIN-rail alternative: HDR-100-24N ($29.80). Load ≈ 1.1 A heater + ~0.8 A Pi. |
| G2 | IEC C13 power cord | 1 | any | ~5 | |
| G3 | 18 AWG heater wire (PTFE or silicone), hookup wire, ferrules, heat-shrink | 1 set | any | ~25 | Twist the heater pair. |

## I. Controller box, connectors, bonding

Part numbers depend on decision D5 (LEMO or M12) in TODO.md.

| # | Item | Qty | Part number / vendor | ~Unit $ | Notes |
|---|---|---:|---|---:|---|
| I1 | Aluminum enclosure for the controller electronics | 1 | e.g. Hammond 1590/1455 series, or a 2U rack box | 40–120 | Holds the Pi, 4 × MAX31865, DAC, INA260, relay, driver + heatsink, DC-DC, fuses; LCD on the front. |
| I2 | 4-pin panel receptacle, sensor (LEMO or M12 A-coded) | 8 | per D5 | 10–60 | 4 on the controller box, 4 on the divider box. |
| I3 | 4-pin cable plug, sensor | 8 | per D5 | 10–60 | Both ends of the 4 PT100 cables. |
| I4 | 2- or 3-pin heater connector, **different type or keying** than I2 | 2 + 2 | per D5 | 10–40 | Rated ≥ 3 A. |
| I5 | 24 V input connector for the controller box | 1 | to match G1's 2.5 × 5.5 mm barrel plug, or a 2-pin panel connector | ~5 | |
| I6 | USB-C pigtail (power-only) for the Pi | 1 | any | ~8 | Feeds 5 V from the DC-DC to the Pi's USB-C input. |
| I7 | PE studs, braided bonding straps, ring lugs | 1 set | any | ~20 | Divider-box panel bonding and the controller-box PE. |
| I8 | DIN rail, terminal blocks, M2.5/M3 standoffs | 1 set | any | ~25 | |

## H. Prototype only (skip if the lab has a programmable supply)

| # | Item | Qty | Part number | ~Unit $ | Notes |
|---|---|---:|---|---:|---|
| H1 | Programmable **linear** DC supply, LAN + SCPI | 1 | Siglent **SPD1305X** (30 V / 5 A; [Siglent NA](https://siglentna.com/power-supplies/spd1000x-series-programmable-dc-power-supply/)) | 328 | `mode = "scpi"`. Rigol DP811A (~$694) is an alternative. |

## Not ordering now

- **Fan:** only if the PT100 gradient data show natural convection is
  insufficient.
- **Dry N₂ / desiccant / gaskets:** only if humidity data require them.
- **Final heater geometry:** E2 may be replaced by a custom-size heater after
  the fixed-power tests.

## Rough total

About **$1,300–1,800** for sections A–G and I, excluding the divider enclosure,
the bench supply (H) and the reference thermometer. The biggest items are the
PT100s (~$450–500) and the connectors (which depend on D5).
