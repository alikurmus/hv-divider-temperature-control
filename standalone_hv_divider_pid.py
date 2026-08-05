#!/usr/bin/env python3
"""Standalone temperature controller for the Project 8 HV-divider enclosure.

Control concept
---------------
The thermal plant is modeled as

    C dT/dt = P_heater - G (T - T_ambient),

which is the physical version of the notebook example "Heating a Room with
Thermal Loss".  The PI/PID controller calculates a requested heater POWER in
watts.  The hardware interface remains a CURRENT command:

    I_command = sqrt(P_command / R_heater).

This keeps the existing current-controlled heater convention while making the
controller gains directly describe thermal power.

The program can run in three modes:

1. simulate: no hardware; useful for checking configuration and logging.
2. dac: MAX31865 PT100 readout + MCP4725 analog current command + optional
   INA260 current/voltage/power readback.
3. scpi: MAX31865 PT100 readout + a programmable current supply controlled
   through PyVISA/SCPI.  Supply-specific SCPI strings are configurable.

Safety philosophy
-----------------
Software is not the only safety layer.  The heater circuit must also include a
normally-closed thermostat or thermal cutoff in series with the heater, a fuse,
and a normally-off hardware enable/relay.  Any sensor failure, stale reading,
over-temperature condition, uncaught exception, or process exit commands zero
current and disables the heater output.
"""

from __future__ import annotations

import argparse
import atexit
import csv
import logging
import math
import signal
import statistics
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Optional, Protocol

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 fallback
    import tomli as tomllib  # type: ignore

LOG = logging.getLogger("hv-divider-pid")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def finite(value: float) -> bool:
    return math.isfinite(float(value))


@dataclass
class ControlConfig:
    setpoint_c: float = 28.0
    period_s: float = 1.0

    # Gains are in POWER units because the controller calculates watts.
    kp_w_per_c: float = 1.0
    ki_w_per_c_s: float = 0.002
    kd_w_s_per_c: float = 0.0
    power_bias_w: float = 0.0

    max_power_w: float = 25.0
    max_current_a: float = 1.05
    heater_resistance_ohm: float = 23.04
    current_slew_a_per_s: float = 0.05

    # Filtering and controller state limits.
    temperature_filter_tau_s: float = 5.0
    derivative_filter_tau_s: float = 10.0
    integral_limit_c_s: float = 5000.0

    # Safety limits.
    overtemperature_c: float = 31.0
    minimum_valid_temperature_c: float = -20.0
    maximum_valid_temperature_c: float = 60.0
    sensor_timeout_s: float = 5.0
    startup_valid_samples: int = 5

    # Performance reporting. Ripple is rolling peak-to-peak temperature.
    ripple_window_s: float = 600.0
    ripple_requirement_c: float = 0.10
    stable_error_band_c: float = 0.05

    # Sensor calibration: calibrated = slope * raw + offset.
    temperature_calibration_slope: float = 1.0
    temperature_calibration_offset_c: float = 0.0


@dataclass
class HardwareConfig:
    mode: str = "simulate"  # simulate, dac, or scpi

    # MAX31865 / PT100
    rtd_cs_pin: str = "D5"
    rtd_wires: int = 4
    rtd_nominal_ohm: float = 100.0
    rtd_reference_ohm: float = 430.0
    rtd_samples_per_read: int = 5
    rtd_sample_spacing_s: float = 0.05

    # DAC current command. The DAC only commands an external current driver.
    dac_i2c_address: int = 0x60
    current_driver_full_scale_a: float = 1.05

    # INA260 optional readback.
    use_ina260: bool = True
    ina260_i2c_address: int = 0x40

    # GPIOs use BCM numbering through gpiozero.
    output_enable_gpio: Optional[int] = 17
    fan_enable_gpio: Optional[int] = 27
    enable_active_high: bool = True
    fan_active_high: bool = True

    # Optional 20x4 I2C LCD using PCF8574 backpack.
    use_lcd: bool = True
    lcd_i2c_address: int = 0x27
    lcd_columns: int = 20
    lcd_rows: int = 4

    # Generic SCPI supply configuration.
    visa_resource: str = ""
    scpi_set_current: str = "SOUR:CURR {value:.6f}"
    scpi_output_on: str = "OUTP ON"
    scpi_output_off: str = "OUTP OFF"
    scpi_measure_current: str = "MEAS:CURR?"
    scpi_measure_voltage: str = "MEAS:VOLT?"
    scpi_timeout_ms: int = 2000


@dataclass
class LoggingConfig:
    csv_path: str = "/var/log/hv-divider-pid/controller.csv"
    log_level: str = "INFO"


@dataclass
class SimulationConfig:
    ambient_c: float = 22.0
    initial_temperature_c: float = 22.0
    thermal_capacitance_j_per_c: float = 3000.0
    thermal_conductance_w_per_c: float = 0.60
    sensor_noise_std_c: float = 0.005


@dataclass
class AppConfig:
    control: ControlConfig = field(default_factory=ControlConfig)
    hardware: HardwareConfig = field(default_factory=HardwareConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)

    @staticmethod
    def from_toml(path: Path) -> "AppConfig":
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
        return AppConfig(
            control=ControlConfig(**raw.get("control", {})),
            hardware=HardwareConfig(**raw.get("hardware", {})),
            logging=LoggingConfig(**raw.get("logging", {})),
            simulation=SimulationConfig(**raw.get("simulation", {})),
        )


@dataclass
class ElectricalReadback:
    current_a: Optional[float] = None
    voltage_v: Optional[float] = None
    power_w: Optional[float] = None


@dataclass
class ControllerTerms:
    error_c: float
    p_w: float
    i_w: float
    d_w: float
    unsaturated_power_w: float
    commanded_power_w: float
    commanded_current_a: float


@dataclass
class StatusSnapshot:
    timestamp: datetime
    raw_temperature_c: float
    filtered_temperature_c: float
    setpoint_c: float
    terms: ControllerTerms
    readback: ElectricalReadback
    ripple_pp_c: Optional[float]
    status: str


class TemperatureSensor(Protocol):
    def read_celsius(self) -> float: ...


class CurrentActuator(Protocol):
    def enable(self) -> None: ...
    def disable(self) -> None: ...
    def set_current_a(self, current_a: float) -> None: ...
    def readback(self) -> ElectricalReadback: ...
    def close(self) -> None: ...


class Display(Protocol):
    def update(self, snapshot: StatusSnapshot) -> None: ...
    def show_fault(self, message: str) -> None: ...
    def close(self) -> None: ...


class Max31865Pt100Sensor:
    """4-wire PT100 sensor read using an MAX31865 SPI interface."""

    def __init__(self, cfg: HardwareConfig):
        try:
            import board
            import digitalio
            import adafruit_max31865
        except ImportError as exc:
            raise RuntimeError(
                "MAX31865 mode requires adafruit-blinka and "
                "adafruit-circuitpython-max31865"
            ) from exc

        if cfg.rtd_wires not in (2, 3, 4):
            raise ValueError("rtd_wires must be 2, 3, or 4")

        pin = getattr(board, cfg.rtd_cs_pin, None)
        if pin is None:
            raise ValueError(f"Unknown board pin name: {cfg.rtd_cs_pin}")

        spi = board.SPI()
        cs = digitalio.DigitalInOut(pin)
        self._sensor = adafruit_max31865.MAX31865(
            spi,
            cs,
            rtd_nominal=cfg.rtd_nominal_ohm,
            ref_resistor=cfg.rtd_reference_ohm,
            wires=cfg.rtd_wires,
        )
        self._samples = max(1, int(cfg.rtd_samples_per_read))
        self._spacing = max(0.0, float(cfg.rtd_sample_spacing_s))

    def read_celsius(self) -> float:
        readings: list[float] = []
        for index in range(self._samples):
            value = float(self._sensor.temperature)
            if finite(value):
                readings.append(value)
            if index + 1 < self._samples and self._spacing > 0:
                time.sleep(self._spacing)
        if not readings:
            raise RuntimeError("MAX31865 returned no finite PT100 readings")
        return statistics.median(readings)


class _GpioOutputs:
    def __init__(self, cfg: HardwareConfig):
        self.enable_device = None
        self.fan_device = None
        try:
            from gpiozero import OutputDevice
        except ImportError:
            if cfg.output_enable_gpio is not None or cfg.fan_enable_gpio is not None:
                raise RuntimeError("GPIO outputs require gpiozero")
            return

        if cfg.output_enable_gpio is not None:
            self.enable_device = OutputDevice(
                cfg.output_enable_gpio,
                active_high=cfg.enable_active_high,
                initial_value=False,
            )
        if cfg.fan_enable_gpio is not None:
            self.fan_device = OutputDevice(
                cfg.fan_enable_gpio,
                active_high=cfg.fan_active_high,
                initial_value=False,
            )

    def heater_enable(self) -> None:
        if self.enable_device is not None:
            self.enable_device.on()

    def heater_disable(self) -> None:
        if self.enable_device is not None:
            self.enable_device.off()

    def fan_enable(self) -> None:
        if self.fan_device is not None:
            self.fan_device.on()

    def close(self) -> None:
        self.heater_disable()
        if self.fan_device is not None:
            self.fan_device.off()
            self.fan_device.close()
        if self.enable_device is not None:
            self.enable_device.close()


class Ina260Monitor:
    def __init__(self, cfg: HardwareConfig, i2c: Any):
        self._sensor = None
        if not cfg.use_ina260:
            return
        try:
            import adafruit_ina260
        except ImportError as exc:
            raise RuntimeError(
                "INA260 readback requires adafruit-circuitpython-ina260"
            ) from exc
        self._sensor = adafruit_ina260.INA260(i2c, address=cfg.ina260_i2c_address)

    def read(self) -> ElectricalReadback:
        if self._sensor is None:
            return ElectricalReadback()
        return ElectricalReadback(
            current_a=float(self._sensor.current) / 1000.0,
            voltage_v=float(self._sensor.voltage),
            power_w=float(self._sensor.power) / 1000.0,
        )


class DacCurrentActuator:
    """MCP4725 command output for an external analog current driver.

    IMPORTANT: the MCP4725 cannot drive the heater.  Its 0-3.3 V output must be
    connected to the command input of a current-regulated power stage whose
    full-scale current matches current_driver_full_scale_a.
    """

    def __init__(self, cfg: HardwareConfig):
        try:
            import board
            import adafruit_mcp4725
        except ImportError as exc:
            raise RuntimeError(
                "DAC mode requires adafruit-blinka and "
                "adafruit-circuitpython-mcp4725"
            ) from exc

        self._cfg = cfg
        self._i2c = board.I2C()
        self._dac = adafruit_mcp4725.MCP4725(
            self._i2c, address=cfg.dac_i2c_address
        )
        self._gpio = _GpioOutputs(cfg)
        self._monitor = Ina260Monitor(cfg, self._i2c)
        self._enabled = False
        self.set_current_a(0.0)
        self._gpio.fan_enable()

    def enable(self) -> None:
        if self._enabled:
            return
        self.set_current_a(0.0)
        self._gpio.heater_enable()
        self._enabled = True

    def disable(self) -> None:
        try:
            self.set_current_a(0.0)
        finally:
            self._gpio.heater_disable()
            self._enabled = False

    def set_current_a(self, current_a: float) -> None:
        full_scale = self._cfg.current_driver_full_scale_a
        if full_scale <= 0:
            raise ValueError("current_driver_full_scale_a must be positive")
        normalized = clamp(float(current_a) / full_scale, 0.0, 1.0)
        self._dac.normalized_value = normalized

    def readback(self) -> ElectricalReadback:
        return self._monitor.read()

    def close(self) -> None:
        self.disable()
        self._gpio.close()


class ScpiCurrentActuator:
    """Generic programmable current supply controlled over PyVISA/SCPI."""

    def __init__(self, cfg: HardwareConfig):
        if not cfg.visa_resource:
            raise ValueError("hardware.visa_resource is required in scpi mode")
        try:
            import pyvisa
        except ImportError as exc:
            raise RuntimeError("SCPI mode requires pyvisa and pyvisa-py") from exc

        self._cfg = cfg
        self._rm = pyvisa.ResourceManager("@py")
        self._instrument = self._rm.open_resource(cfg.visa_resource)
        self._instrument.timeout = cfg.scpi_timeout_ms
        self._gpio = _GpioOutputs(cfg)
        self._gpio.fan_enable()
        self._enabled = False
        self.disable()

    def enable(self) -> None:
        if self._enabled:
            return
        self.set_current_a(0.0)
        self._gpio.heater_enable()
        self._instrument.write(self._cfg.scpi_output_on)
        self._enabled = True

    def disable(self) -> None:
        try:
            self.set_current_a(0.0)
            if self._enabled:
                self._instrument.write(self._cfg.scpi_output_off)
        finally:
            self._gpio.heater_disable()
            self._enabled = False

    def set_current_a(self, current_a: float) -> None:
        command = self._cfg.scpi_set_current.format(value=float(current_a))
        self._instrument.write(command)

    def readback(self) -> ElectricalReadback:
        current = float(self._instrument.query(self._cfg.scpi_measure_current).strip())
        voltage = float(self._instrument.query(self._cfg.scpi_measure_voltage).strip())
        return ElectricalReadback(
            current_a=current,
            voltage_v=voltage,
            power_w=current * voltage,
        )

    def close(self) -> None:
        try:
            self.disable()
        finally:
            self._instrument.close()
            self._rm.close()
            self._gpio.close()


class SimulatedPlant(TemperatureSensor, CurrentActuator):
    def __init__(self, cfg: AppConfig):
        import random

        self._random = random.Random(12345)
        self._sim = cfg.simulation
        self._control = cfg.control
        self._temperature_c = self._sim.initial_temperature_c
        self._current_a = 0.0
        self._enabled = False
        self._last_time = time.monotonic()

    def _step(self) -> None:
        now = time.monotonic()
        dt = max(0.0, now - self._last_time)
        self._last_time = now
        current = self._current_a if self._enabled else 0.0
        power = current * current * self._control.heater_resistance_ohm
        heat_loss = self._sim.thermal_conductance_w_per_c * (
            self._temperature_c - self._sim.ambient_c
        )
        dtdt = (power - heat_loss) / self._sim.thermal_capacitance_j_per_c
        self._temperature_c += dtdt * dt

    def read_celsius(self) -> float:
        self._step()
        return self._temperature_c + self._random.gauss(
            0.0, self._sim.sensor_noise_std_c
        )

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._current_a = 0.0
        self._enabled = False

    def set_current_a(self, current_a: float) -> None:
        self._step()
        self._current_a = max(0.0, float(current_a))

    def readback(self) -> ElectricalReadback:
        self._step()
        current = self._current_a if self._enabled else 0.0
        voltage = current * self._control.heater_resistance_ohm
        return ElectricalReadback(
            current_a=current,
            voltage_v=voltage,
            power_w=current * voltage,
        )

    def close(self) -> None:
        self.disable()


class ConsoleDisplay:
    def update(self, snapshot: StatusSnapshot) -> None:
        rb = snapshot.readback
        current = rb.current_a if rb.current_a is not None else snapshot.terms.commanded_current_a
        power = rb.power_w if rb.power_w is not None else snapshot.terms.commanded_power_w
        ripple = "--" if snapshot.ripple_pp_c is None else f"{snapshot.ripple_pp_c:.3f}"
        LOG.info(
            "Traw=%.4f C Tfilt=%.4f C SP=%.3f C Icmd=%.4f A "
            "Imeas=%s A P=%s W ripple_pp=%s C status=%s",
            snapshot.raw_temperature_c,
            snapshot.filtered_temperature_c,
            snapshot.setpoint_c,
            snapshot.terms.commanded_current_a,
            "--" if current is None else f"{current:.4f}",
            "--" if power is None else f"{power:.3f}",
            ripple,
            snapshot.status,
        )

    def show_fault(self, message: str) -> None:
        LOG.error("DISPLAY FAULT: %s", message)

    def close(self) -> None:
        return


class Lcd20x4Display:
    def __init__(self, cfg: HardwareConfig):
        try:
            from RPLCD.i2c import CharLCD
        except ImportError as exc:
            raise RuntimeError("LCD support requires RPLCD and smbus2") from exc
        self._lcd = CharLCD(
            i2c_expander="PCF8574",
            address=cfg.lcd_i2c_address,
            port=1,
            cols=cfg.lcd_columns,
            rows=cfg.lcd_rows,
            charmap="A00",
            auto_linebreaks=False,
        )
        self._cols = cfg.lcd_columns
        self._rows = cfg.lcd_rows
        self._lcd.clear()

    def _line(self, row: int, text: str) -> None:
        if row >= self._rows:
            return
        self._lcd.cursor_pos = (row, 0)
        self._lcd.write_string(text[: self._cols].ljust(self._cols))

    def update(self, snapshot: StatusSnapshot) -> None:
        rb = snapshot.readback
        imeas = rb.current_a
        power = rb.power_w
        ripple = snapshot.ripple_pp_c
        self._line(
            0,
            f"T {snapshot.filtered_temperature_c:6.3f}  SP {snapshot.setpoint_c:5.2f}",
        )
        self._line(
            1,
            f"Icmd {snapshot.terms.commanded_current_a:5.3f} A",
        )
        self._line(
            2,
            f"I {('--' if imeas is None else f'{imeas:.3f}')}A "
            f"P {('--' if power is None else f'{power:.2f}')}W",
        )
        self._line(
            3,
            f"Rip {('--' if ripple is None else f'{ripple:.3f}')}C {snapshot.status}",
        )

    def show_fault(self, message: str) -> None:
        self._lcd.clear()
        self._line(0, "*** HEATER OFF ***")
        self._line(1, "FAULT")
        self._line(2, message)

    def close(self) -> None:
        try:
            self._lcd.clear()
        finally:
            self._lcd.close(clear=True)


class CompositeDisplay:
    def __init__(self, displays: list[Display]):
        self._displays = displays

    def update(self, snapshot: StatusSnapshot) -> None:
        for display in self._displays:
            try:
                display.update(snapshot)
            except Exception:
                LOG.exception("Display update failed")

    def show_fault(self, message: str) -> None:
        for display in self._displays:
            try:
                display.show_fault(message)
            except Exception:
                LOG.exception("Display fault update failed")

    def close(self) -> None:
        for display in self._displays:
            try:
                display.close()
            except Exception:
                LOG.exception("Display close failed")


class PowerPid:
    """PI/PID in power units with anti-windup and derivative on measurement."""

    def __init__(self, cfg: ControlConfig):
        self.cfg = cfg
        self.integral_c_s = 0.0
        self.filtered_temperature_c: Optional[float] = None
        self.filtered_dtdt_c_per_s = 0.0
        self.last_filtered_temperature_c: Optional[float] = None
        self.last_current_a = 0.0

    def reset(self) -> None:
        self.integral_c_s = 0.0
        self.filtered_temperature_c = None
        self.filtered_dtdt_c_per_s = 0.0
        self.last_filtered_temperature_c = None
        self.last_current_a = 0.0

    def _filter_temperature(self, raw_temperature_c: float, dt: float) -> float:
        if self.filtered_temperature_c is None:
            self.filtered_temperature_c = raw_temperature_c
            return raw_temperature_c
        tau = max(0.0, self.cfg.temperature_filter_tau_s)
        alpha = 1.0 if tau == 0 else dt / (tau + dt)
        self.filtered_temperature_c += alpha * (
            raw_temperature_c - self.filtered_temperature_c
        )
        return self.filtered_temperature_c

    def update(self, raw_temperature_c: float, dt: float) -> ControllerTerms:
        dt = max(1e-6, float(dt))
        temperature_c = self._filter_temperature(raw_temperature_c, dt)
        error_c = self.cfg.setpoint_c - temperature_c

        if self.last_filtered_temperature_c is None:
            raw_dtdt = 0.0
        else:
            raw_dtdt = (
                temperature_c - self.last_filtered_temperature_c
            ) / dt
        self.last_filtered_temperature_c = temperature_c

        d_tau = max(0.0, self.cfg.derivative_filter_tau_s)
        d_alpha = 1.0 if d_tau == 0 else dt / (d_tau + dt)
        self.filtered_dtdt_c_per_s += d_alpha * (
            raw_dtdt - self.filtered_dtdt_c_per_s
        )

        p_w = self.cfg.kp_w_per_c * error_c
        d_w = -self.cfg.kd_w_s_per_c * self.filtered_dtdt_c_per_s

        # First evaluate with the existing integral state.
        i_w = self.cfg.ki_w_per_c_s * self.integral_c_s
        unsaturated = self.cfg.power_bias_w + p_w + i_w + d_w
        saturated = clamp(unsaturated, 0.0, self.cfg.max_power_w)

        # Conditional integration: integrate only when not saturated, or when the
        # error would drive the output back toward the allowed range.
        integrate = (
            0.0 < unsaturated < self.cfg.max_power_w
            or (unsaturated <= 0.0 and error_c > 0.0)
            or (unsaturated >= self.cfg.max_power_w and error_c < 0.0)
        )
        if integrate and self.cfg.ki_w_per_c_s != 0.0:
            self.integral_c_s += error_c * dt
            limit = abs(self.cfg.integral_limit_c_s)
            self.integral_c_s = clamp(self.integral_c_s, -limit, limit)
            i_w = self.cfg.ki_w_per_c_s * self.integral_c_s
            unsaturated = self.cfg.power_bias_w + p_w + i_w + d_w
            saturated = clamp(unsaturated, 0.0, self.cfg.max_power_w)

        resistance = self.cfg.heater_resistance_ohm
        if resistance <= 0:
            raise ValueError("heater_resistance_ohm must be positive")
        current = math.sqrt(max(0.0, saturated) / resistance)
        current = min(current, self.cfg.max_current_a)

        # Current slew limiting avoids abrupt electrical and thermal steps.
        maximum_change = max(0.0, self.cfg.current_slew_a_per_s) * dt
        current = clamp(
            current,
            max(0.0, self.last_current_a - maximum_change),
            self.last_current_a + maximum_change,
        )
        self.last_current_a = current

        # Current limiting can reduce actual command power below the PI request.
        commanded_power = min(saturated, current * current * resistance)

        return ControllerTerms(
            error_c=error_c,
            p_w=p_w,
            i_w=i_w,
            d_w=d_w,
            unsaturated_power_w=unsaturated,
            commanded_power_w=commanded_power,
            commanded_current_a=current,
        )


class CsvLogger:
    HEADER = [
        "timestamp_utc",
        "raw_temperature_c",
        "filtered_temperature_c",
        "setpoint_c",
        "error_c",
        "p_term_w",
        "i_term_w",
        "d_term_w",
        "commanded_power_w",
        "commanded_current_a",
        "measured_current_a",
        "measured_voltage_v",
        "measured_power_w",
        "ripple_peak_to_peak_c",
        "status",
    ]

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists() or self.path.stat().st_size == 0
        self._file = self.path.open("a", newline="", buffering=1)
        self._writer = csv.writer(self._file)
        if new_file:
            self._writer.writerow(self.HEADER)

    def write(self, snapshot: StatusSnapshot) -> None:
        rb = snapshot.readback
        terms = snapshot.terms
        self._writer.writerow(
            [
                snapshot.timestamp.isoformat(),
                f"{snapshot.raw_temperature_c:.6f}",
                f"{snapshot.filtered_temperature_c:.6f}",
                f"{snapshot.setpoint_c:.6f}",
                f"{terms.error_c:.6f}",
                f"{terms.p_w:.6f}",
                f"{terms.i_w:.6f}",
                f"{terms.d_w:.6f}",
                f"{terms.commanded_power_w:.6f}",
                f"{terms.commanded_current_a:.6f}",
                "" if rb.current_a is None else f"{rb.current_a:.6f}",
                "" if rb.voltage_v is None else f"{rb.voltage_v:.6f}",
                "" if rb.power_w is None else f"{rb.power_w:.6f}",
                "" if snapshot.ripple_pp_c is None else f"{snapshot.ripple_pp_c:.6f}",
                snapshot.status,
            ]
        )

    def close(self) -> None:
        self._file.flush()
        self._file.close()


class StandaloneTemperatureController:
    def __init__(
        self,
        cfg: AppConfig,
        sensor: TemperatureSensor,
        actuator: CurrentActuator,
        display: Display,
    ):
        self.cfg = cfg
        self.sensor = sensor
        self.actuator = actuator
        self.display = display
        self.pid = PowerPid(cfg.control)
        self.csv = CsvLogger(cfg.logging.csv_path)
        self._stop = False
        self._fault_latched = False
        self._valid_samples = 0
        self._ripple_samples: Deque[tuple[float, float]] = deque()
        self._last_good_sensor_time: Optional[float] = None
        self._last_loop_time = time.monotonic()
        self._closed = False

        atexit.register(self.close)
        signal.signal(signal.SIGTERM, self._signal_stop)
        signal.signal(signal.SIGINT, self._signal_stop)

    def _signal_stop(self, signum: int, _frame: Any) -> None:
        LOG.warning("Received signal %s; shutting down heater", signum)
        self._stop = True

    def _validate_temperature(self, temperature_c: float) -> None:
        c = self.cfg.control
        if not finite(temperature_c):
            raise RuntimeError("PT100 temperature is non-finite")
        if not c.minimum_valid_temperature_c <= temperature_c <= c.maximum_valid_temperature_c:
            raise RuntimeError(
                f"PT100 temperature {temperature_c:.3f} C is outside valid range"
            )
        if temperature_c >= c.overtemperature_c:
            raise RuntimeError(
                f"over-temperature: {temperature_c:.3f} C >= {c.overtemperature_c:.3f} C"
            )

    def _calibrate(self, raw_c: float) -> float:
        c = self.cfg.control
        return c.temperature_calibration_slope * raw_c + c.temperature_calibration_offset_c

    def _update_ripple(self, now: float, temperature_c: float) -> Optional[float]:
        window = self.cfg.control.ripple_window_s
        self._ripple_samples.append((now, temperature_c))
        while self._ripple_samples and now - self._ripple_samples[0][0] > window:
            self._ripple_samples.popleft()
        if len(self._ripple_samples) < 2:
            return None
        values = [sample[1] for sample in self._ripple_samples]
        return max(values) - min(values)

    def _status(self, terms: ControllerTerms, ripple: Optional[float]) -> str:
        c = self.cfg.control
        if self._valid_samples < c.startup_valid_samples:
            return "START"
        if abs(terms.error_c) > c.stable_error_band_c:
            return "RAMP"
        if ripple is None:
            return "WAIT"
        return "STABLE" if ripple < c.ripple_requirement_c else "RIPPLE"

    def _trip(self, message: str) -> None:
        self._fault_latched = True
        LOG.critical("HEATER FAULT: %s", message)
        try:
            self.actuator.disable()
        finally:
            self.display.show_fault(message)

    def run(self) -> None:
        c = self.cfg.control
        LOG.info("Controller starting with setpoint %.3f C", c.setpoint_c)
        self.actuator.disable()

        while not self._stop and not self._fault_latched:
            loop_started = time.monotonic()
            dt = max(1e-6, loop_started - self._last_loop_time)
            self._last_loop_time = loop_started

            try:
                sensor_started = time.monotonic()
                sensor_raw = self.sensor.read_celsius()
                sensor_elapsed = time.monotonic() - sensor_started
                if sensor_elapsed > c.sensor_timeout_s:
                    raise RuntimeError(
                        f"PT100 read exceeded timeout: {sensor_elapsed:.2f} s"
                    )
                temperature_c = self._calibrate(sensor_raw)
                self._validate_temperature(temperature_c)
                self._last_good_sensor_time = loop_started
                self._valid_samples += 1

                terms = self.pid.update(temperature_c, dt)

                # Keep the heater disabled until several consecutive valid RTD
                # samples have been received after startup.
                if self._valid_samples < c.startup_valid_samples:
                    self.actuator.disable()
                    terms.commanded_current_a = 0.0
                    terms.commanded_power_w = 0.0
                else:
                    self.actuator.enable()
                    self.actuator.set_current_a(terms.commanded_current_a)

                readback = self.actuator.readback()
                if readback.power_w is None:
                    measured_i = (
                        readback.current_a
                        if readback.current_a is not None
                        else terms.commanded_current_a
                    )
                    readback.power_w = measured_i * measured_i * c.heater_resistance_ohm

                filtered = self.pid.filtered_temperature_c
                assert filtered is not None
                ripple = self._update_ripple(loop_started, temperature_c)
                status = self._status(terms, ripple)
                snapshot = StatusSnapshot(
                    timestamp=datetime.now(timezone.utc),
                    raw_temperature_c=temperature_c,
                    filtered_temperature_c=filtered,
                    setpoint_c=c.setpoint_c,
                    terms=terms,
                    readback=readback,
                    ripple_pp_c=ripple,
                    status=status,
                )
                self.csv.write(snapshot)
                self.display.update(snapshot)

            except Exception as exc:
                self._trip(str(exc))
                break

            elapsed = time.monotonic() - loop_started
            time.sleep(max(0.0, c.period_s - elapsed))

        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.actuator.disable()
        except Exception:
            LOG.exception("Failed to disable heater during shutdown")
        try:
            self.actuator.close()
        except Exception:
            LOG.exception("Failed to close actuator")
        try:
            self.display.close()
        except Exception:
            LOG.exception("Failed to close display")
        try:
            self.csv.close()
        except Exception:
            LOG.exception("Failed to close CSV log")


def build_hardware(cfg: AppConfig) -> tuple[TemperatureSensor, CurrentActuator]:
    mode = cfg.hardware.mode.strip().lower()
    if mode == "simulate":
        plant = SimulatedPlant(cfg)
        return plant, plant

    sensor = Max31865Pt100Sensor(cfg.hardware)
    if mode == "dac":
        actuator: CurrentActuator = DacCurrentActuator(cfg.hardware)
    elif mode == "scpi":
        actuator = ScpiCurrentActuator(cfg.hardware)
    else:
        raise ValueError("hardware.mode must be simulate, dac, or scpi")
    return sensor, actuator


def build_display(cfg: AppConfig) -> Display:
    displays: list[Display] = [ConsoleDisplay()]
    if cfg.hardware.use_lcd and cfg.hardware.mode.lower() != "simulate":
        displays.append(Lcd20x4Display(cfg.hardware))
    return CompositeDisplay(displays)


def configure_logging(level: str) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to TOML configuration file",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Override hardware.mode and run the thermal simulation",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = AppConfig.from_toml(args.config)
    if args.simulate:
        cfg.hardware.mode = "simulate"
        cfg.hardware.use_lcd = False
        if cfg.logging.csv_path.startswith("/var/log/"):
            cfg.logging.csv_path = "./controller_simulation.csv"
    configure_logging(cfg.logging.log_level)

    sensor, actuator = build_hardware(cfg)
    display = build_display(cfg)
    controller = StandaloneTemperatureController(cfg, sensor, actuator, display)
    controller.run()
    return 1 if controller._fault_latched else 0


if __name__ == "__main__":
    sys.exit(main())
