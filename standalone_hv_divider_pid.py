#!/usr/bin/env python3
"""Standalone temperature controller for the Project 8 HV-divider enclosure.

The controller is intentionally standalone: slow controls are not required for
regulation.  A future slow-controls link can monitor the local controller, but
loss of that link must not stop local temperature regulation.

Control concept
---------------
The thermal plant is modeled as

    C dT/dt = P_heater - G (T - T_ambient),

which is the physical version of the notebook example "Heating a Room with
Thermal Loss".  The PI/PID controller calculates a requested heater POWER in
watts.  The heater hardware remains current-controlled:

    I_command = sqrt(P_command / R_heater).

The code supports four PT100 roles:

* control_air: the only sensor used by the PI/PID loop;
* monitor_air: a second air sensor used to verify regulation and gradients;
* ground_board: a sensor attached to the divider ground board;
* spare: an additional monitored PT100 for redundancy/diagnostics.

The monitoring sensors are deliberately not used for automatic control-sensor
failover.  A failed control sensor shuts the heater off; automatic failover can
be added later only after sensor placement/calibration policy is agreed.

Optional environmental/peripheral monitoring includes:

* MAX31865 hardware fault status for every PT100 channel;
* an SHT31-D relative-humidity sensor;
* a fixed-speed fan with tachometer feedback (no PWM/frequency speed control);
* a 20x4 LCD with a continuously changing heartbeat character.

Safety philosophy
-----------------
Software is not the only safety layer.  The heater circuit must also include a
normally-closed thermostat or thermal cutoff in series with the heater, a fuse,
and a normally-off hardware enable/relay.  Any control-sensor failure,
over-temperature condition, uncaught exception, or process exit commands zero
current and disables the heater output.  Healthy monitor sensors can also trip
on over-temperature when configured to do so.
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
import threading
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
    trip_on_monitor_overtemperature: bool = True

    # Performance reporting. Ripple is rolling peak-to-peak control temperature.
    ripple_window_s: float = 600.0
    ripple_requirement_c: float = 0.10
    stable_error_band_c: float = 0.05

    # Monitoring warnings do not stop the heater unless a safety limit is hit.
    air_sensor_disagreement_warning_c: float = 0.20
    humidity_warning_rh: float = 50.0

    # Control PT100 calibration: calibrated = slope * raw + offset.
    temperature_calibration_slope: float = 1.0
    temperature_calibration_offset_c: float = 0.0


@dataclass
class HardwareConfig:
    mode: str = "simulate"  # simulate, dac, or scpi

    # Shared MAX31865 / PT100 configuration.
    rtd_wires: int = 4
    rtd_nominal_ohm: float = 100.0
    rtd_reference_ohm: float = 430.0
    rtd_samples_per_read: int = 3
    rtd_sample_spacing_s: float = 0.02

    # Four proposed PT100 roles.  Each MAX31865 shares SPI clock/data lines but
    # has its own chip-select pin.
    control_rtd_cs_pin: str = "D5"
    use_monitor_air_rtd: bool = True
    monitor_air_rtd_cs_pin: str = "D6"
    monitor_air_calibration_slope: float = 1.0
    monitor_air_calibration_offset_c: float = 0.0

    use_ground_board_rtd: bool = True
    ground_board_rtd_cs_pin: str = "D13"
    ground_board_calibration_slope: float = 1.0
    ground_board_calibration_offset_c: float = 0.0

    use_spare_rtd: bool = True
    spare_rtd_cs_pin: str = "D19"
    spare_calibration_slope: float = 1.0
    spare_calibration_offset_c: float = 0.0

    # Optional SHT31-D environmental monitor.  Monitoring only; humidity does
    # not directly drive the heater.
    use_humidity_sensor: bool = False
    humidity_i2c_address: int = 0x44

    # DAC current command. The DAC only commands an external current driver.
    dac_i2c_address: int = 0x60
    current_driver_full_scale_a: float = 1.05

    # INA260 optional readback.
    use_ina260: bool = True
    ina260_i2c_address: int = 0x40

    # Heater output enable. GPIO numbers use BCM numbering through gpiozero.
    output_enable_gpio: Optional[int] = 17
    enable_active_high: bool = True

    # Fan is OPTIONAL.  Baseline design is natural convection.  If installed,
    # it is only switched on/off at fixed speed; there is no PWM/frequency speed
    # command in this program.  Set fan_tach_gpio < 0 to disable tach readback.
    use_fan: bool = False
    fan_required: bool = False
    fan_enable_gpio: int = 27
    fan_active_high: bool = True
    fan_tach_gpio: int = 22
    fan_tach_pull_up: bool = True
    fan_startup_grace_s: float = 3.0
    fan_tach_window_s: float = 2.0
    fan_min_edges_per_window: int = 2

    # Optional 20x4 I2C LCD using PCF8574 backpack.
    use_lcd: bool = True
    lcd_i2c_address: int = 0x27
    lcd_columns: int = 20
    lcd_rows: int = 4
    lcd_page_period_s: float = 5.0

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
    humidity_rh: float = 35.0


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
class EnvironmentReadings:
    control_air_c: float
    monitor_air_c: Optional[float] = None
    ground_board_c: Optional[float] = None
    spare_c: Optional[float] = None
    humidity_rh: Optional[float] = None
    sensor_faults: dict[str, str] = field(default_factory=dict)


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
    environment: EnvironmentReadings
    filtered_temperature_c: float
    setpoint_c: float
    terms: ControllerTerms
    readback: ElectricalReadback
    ripple_pp_c: Optional[float]
    status: str
    warnings: list[str] = field(default_factory=list)
    fan_spinning: Optional[bool] = None
    # Standalone operation is intentional.  None means no external slow-control
    # protocol has been configured, not a failure.
    slow_controls_connected: Optional[bool] = None


class SensorSuite(Protocol):
    def read_environment(self) -> EnvironmentReadings: ...
    def close(self) -> None: ...


class CurrentActuator(Protocol):
    def enable(self) -> None: ...
    def disable(self) -> None: ...
    def set_current_a(self, current_a: float) -> None: ...
    def readback(self) -> ElectricalReadback: ...
    def close(self) -> None: ...


class Fan(Protocol):
    def start(self) -> None: ...
    def spinning(self) -> Optional[bool]: ...
    def close(self) -> None: ...


class Display(Protocol):
    def update(self, snapshot: StatusSnapshot) -> None: ...
    def show_fault(self, message: str) -> None: ...
    def close(self) -> None: ...


MAX31865_FAULT_NAMES = (
    "HIGHTHRESH",
    "LOWTHRESH",
    "REFINLOW",
    "REFINHIGH",
    "RTDINLOW",
    "OVUV",
)


class _Max31865Channel:
    """One MAX31865/PT100 channel with explicit hardware-fault checks."""

    def __init__(
        self,
        *,
        name: str,
        spi: Any,
        cs_pin_name: str,
        cfg: HardwareConfig,
        slope: float,
        offset_c: float,
    ):
        try:
            import board
            import digitalio
            import adafruit_max31865
        except ImportError as exc:
            raise RuntimeError(
                "PT100 mode requires adafruit-blinka and "
                "adafruit-circuitpython-max31865"
            ) from exc

        if cfg.rtd_wires not in (2, 3, 4):
            raise ValueError("rtd_wires must be 2, 3, or 4")

        pin = getattr(board, cs_pin_name, None)
        if pin is None:
            raise ValueError(f"Unknown board pin name for {name}: {cs_pin_name}")

        self.name = name
        self._cs = digitalio.DigitalInOut(pin)
        self._sensor = adafruit_max31865.MAX31865(
            spi,
            self._cs,
            rtd_nominal=cfg.rtd_nominal_ohm,
            ref_resistor=cfg.rtd_reference_ohm,
            wires=cfg.rtd_wires,
        )
        self._samples = max(1, int(cfg.rtd_samples_per_read))
        self._spacing = max(0.0, float(cfg.rtd_sample_spacing_s))
        self._slope = float(slope)
        self._offset_c = float(offset_c)

    def _fault_text(self) -> Optional[str]:
        fault_tuple = tuple(bool(v) for v in self._sensor.fault)
        active = [
            name for name, state in zip(MAX31865_FAULT_NAMES, fault_tuple) if state
        ]
        if not active:
            return None
        return ",".join(active)

    def read_celsius(self) -> float:
        # Start each transaction with a clear fault register.  Any fault set by
        # the subsequent conversion is then attributable to this read cycle.
        self._sensor.clear_faults()
        readings: list[float] = []
        for index in range(self._samples):
            try:
                value = float(self._sensor.temperature)
            except Exception as exc:
                fault = self._fault_text()
                self._sensor.clear_faults()
                if fault is not None:
                    raise RuntimeError(
                        f"MAX31865 {self.name} fault: {fault}"
                    ) from exc
                raise
            if finite(value):
                readings.append(value)
            if index + 1 < self._samples and self._spacing > 0:
                time.sleep(self._spacing)

        fault = self._fault_text()
        if fault is not None:
            self._sensor.clear_faults()
            raise RuntimeError(f"MAX31865 {self.name} fault: {fault}")
        if not readings:
            raise RuntimeError(f"MAX31865 {self.name} returned no finite readings")

        raw_c = statistics.median(readings)
        return self._slope * raw_c + self._offset_c

    def close(self) -> None:
        try:
            self._cs.deinit()
        except Exception:
            LOG.exception("Failed to close PT100 chip-select for %s", self.name)


class Max31865SensorSuite:
    """Control + monitoring PT100s, with optional SHT31-D humidity readout."""

    def __init__(self, cfg: AppConfig):
        try:
            import board
        except ImportError as exc:
            raise RuntimeError("Hardware sensor mode requires adafruit-blinka") from exc

        self._cfg = cfg
        self._spi = board.SPI()
        c = cfg.control
        h = cfg.hardware

        self._control = _Max31865Channel(
            name="control_air",
            spi=self._spi,
            cs_pin_name=h.control_rtd_cs_pin,
            cfg=h,
            slope=c.temperature_calibration_slope,
            offset_c=c.temperature_calibration_offset_c,
        )
        self._aux: dict[str, _Max31865Channel] = {}
        if h.use_monitor_air_rtd:
            self._aux["monitor_air"] = _Max31865Channel(
                name="monitor_air",
                spi=self._spi,
                cs_pin_name=h.monitor_air_rtd_cs_pin,
                cfg=h,
                slope=h.monitor_air_calibration_slope,
                offset_c=h.monitor_air_calibration_offset_c,
            )
        if h.use_ground_board_rtd:
            self._aux["ground_board"] = _Max31865Channel(
                name="ground_board",
                spi=self._spi,
                cs_pin_name=h.ground_board_rtd_cs_pin,
                cfg=h,
                slope=h.ground_board_calibration_slope,
                offset_c=h.ground_board_calibration_offset_c,
            )
        if h.use_spare_rtd:
            self._aux["spare"] = _Max31865Channel(
                name="spare",
                spi=self._spi,
                cs_pin_name=h.spare_rtd_cs_pin,
                cfg=h,
                slope=h.spare_calibration_slope,
                offset_c=h.spare_calibration_offset_c,
            )

        self._humidity_sensor = None
        self._humidity_i2c = None
        if h.use_humidity_sensor:
            try:
                import adafruit_sht31d
            except ImportError as exc:
                raise RuntimeError(
                    "Humidity monitoring requires adafruit-circuitpython-sht31d"
                ) from exc
            self._humidity_i2c = board.I2C()
            self._humidity_sensor = adafruit_sht31d.SHT31D(
                self._humidity_i2c,
                address=h.humidity_i2c_address,
            )

    def read_environment(self) -> EnvironmentReadings:
        # The control channel is safety-critical.  Propagate any exception so
        # the outer controller trips the heater rather than silently failing over.
        control_c = self._control.read_celsius()
        values: dict[str, Optional[float]] = {
            "monitor_air": None,
            "ground_board": None,
            "spare": None,
        }
        faults: dict[str, str] = {}

        for name, channel in self._aux.items():
            try:
                values[name] = channel.read_celsius()
            except Exception as exc:
                faults[name] = str(exc)
                LOG.warning("Monitoring PT100 %s failed: %s", name, exc)

        humidity_rh: Optional[float] = None
        if self._humidity_sensor is not None:
            try:
                humidity_rh = float(self._humidity_sensor.relative_humidity)
                if not finite(humidity_rh) or not 0.0 <= humidity_rh <= 100.0:
                    raise RuntimeError(f"invalid humidity reading {humidity_rh}")
            except Exception as exc:
                faults["humidity"] = str(exc)
                LOG.warning("Humidity sensor failed: %s", exc)
                humidity_rh = None

        return EnvironmentReadings(
            control_air_c=control_c,
            monitor_air_c=values["monitor_air"],
            ground_board_c=values["ground_board"],
            spare_c=values["spare"],
            humidity_rh=humidity_rh,
            sensor_faults=faults,
        )

    def close(self) -> None:
        self._control.close()
        for channel in self._aux.values():
            channel.close()


class HeaterEnable:
    def __init__(self, cfg: HardwareConfig):
        self._device = None
        if cfg.output_enable_gpio is None:
            return
        try:
            from gpiozero import OutputDevice
        except ImportError as exc:
            raise RuntimeError("Heater enable GPIO requires gpiozero") from exc
        self._device = OutputDevice(
            cfg.output_enable_gpio,
            active_high=cfg.enable_active_high,
            initial_value=False,
        )

    def on(self) -> None:
        if self._device is not None:
            self._device.on()

    def off(self) -> None:
        if self._device is not None:
            self._device.off()

    def close(self) -> None:
        self.off()
        if self._device is not None:
            self._device.close()


class NullFan:
    def start(self) -> None:
        return

    def spinning(self) -> Optional[bool]:
        return None

    def close(self) -> None:
        return


class FixedSpeedFan:
    """Optional fixed-speed fan with edge-based tachometer feedback.

    The output is binary on/off only.  This program does not PWM the fan and
    does not adjust fan frequency or speed.
    """

    def __init__(self, cfg: HardwareConfig):
        try:
            from gpiozero import DigitalInputDevice, OutputDevice
        except ImportError as exc:
            raise RuntimeError("Fan GPIO/tach monitoring requires gpiozero") from exc

        self._cfg = cfg
        self._output = OutputDevice(
            cfg.fan_enable_gpio,
            active_high=cfg.fan_active_high,
            initial_value=False,
        )
        self._tach = None
        self._edge_times: Deque[float] = deque()
        self._lock = threading.Lock()
        self._started_at: Optional[float] = None

        if cfg.fan_tach_gpio >= 0:
            self._tach = DigitalInputDevice(
                cfg.fan_tach_gpio,
                pull_up=cfg.fan_tach_pull_up,
            )
            self._tach.when_activated = self._on_tach_edge
        elif cfg.fan_required:
            raise ValueError("fan_required=true requires fan_tach_gpio >= 0")

    def _on_tach_edge(self) -> None:
        now = time.monotonic()
        with self._lock:
            self._edge_times.append(now)

    def start(self) -> None:
        self._output.on()
        if self._started_at is None:
            self._started_at = time.monotonic()

    def spinning(self) -> Optional[bool]:
        if self._tach is None:
            return None
        now = time.monotonic()
        if self._started_at is None:
            return False
        if now - self._started_at < self._cfg.fan_startup_grace_s:
            return None

        window = max(0.1, self._cfg.fan_tach_window_s)
        with self._lock:
            while self._edge_times and now - self._edge_times[0] > window:
                self._edge_times.popleft()
            return len(self._edge_times) >= max(1, self._cfg.fan_min_edges_per_window)

    def close(self) -> None:
        try:
            self._output.off()
        finally:
            if self._tach is not None:
                self._tach.close()
            self._output.close()


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
    full-scale current matches current_driver_full_scale_a.  Selection of the
    final low-noise current driver remains an open hardware decision.
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
        self._enable = HeaterEnable(cfg)
        self._monitor = Ina260Monitor(cfg, self._i2c)
        self._enabled = False
        self.set_current_a(0.0)

    def enable(self) -> None:
        if self._enabled:
            return
        self.set_current_a(0.0)
        self._enable.on()
        self._enabled = True

    def disable(self) -> None:
        try:
            self.set_current_a(0.0)
        finally:
            self._enable.off()
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
        self._enable.close()


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
        self._enable = HeaterEnable(cfg)
        self._enabled = False
        self.disable()

    def enable(self) -> None:
        if self._enabled:
            return
        self.set_current_a(0.0)
        self._enable.on()
        self._instrument.write(self._cfg.scpi_output_on)
        self._enabled = True

    def disable(self) -> None:
        try:
            self.set_current_a(0.0)
            if self._enabled:
                self._instrument.write(self._cfg.scpi_output_off)
        finally:
            self._enable.off()
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
            self._enable.close()


class SimulatedPlant(SensorSuite, CurrentActuator):
    def __init__(self, cfg: AppConfig):
        import random

        self._random = random.Random(12345)
        self._sim = cfg.simulation
        self._control = cfg.control
        self._hardware = cfg.hardware
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

    def _noise(self) -> float:
        return self._random.gauss(0.0, self._sim.sensor_noise_std_c)

    def read_environment(self) -> EnvironmentReadings:
        self._step()
        t = self._temperature_c
        return EnvironmentReadings(
            control_air_c=t + self._noise(),
            monitor_air_c=(t + 0.010 + self._noise())
            if self._hardware.use_monitor_air_rtd
            else None,
            ground_board_c=(t + 0.020 + self._noise())
            if self._hardware.use_ground_board_rtd
            else None,
            spare_c=(t - 0.010 + self._noise())
            if self._hardware.use_spare_rtd
            else None,
            humidity_rh=self._sim.humidity_rh
            if self._hardware.use_humidity_sensor
            else None,
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
        env = snapshot.environment
        rb = snapshot.readback
        current = (
            rb.current_a
            if rb.current_a is not None
            else snapshot.terms.commanded_current_a
        )
        power = rb.power_w if rb.power_w is not None else snapshot.terms.commanded_power_w
        ripple = "--" if snapshot.ripple_pp_c is None else f"{snapshot.ripple_pp_c:.3f}"
        fan = "--" if snapshot.fan_spinning is None else ("OK" if snapshot.fan_spinning else "FAIL")
        warning_text = "; ".join(snapshot.warnings) if snapshot.warnings else "none"
        LOG.info(
            "Tctl=%.4f C Tfilt=%.4f C Tair2=%s C Tboard=%s C Tspare=%s C "
            "RH=%s %% SP=%.3f C Icmd=%.4f A Imeas=%s A P=%s W "
            "ripple_pp=%s C fan=%s status=%s warnings=%s",
            env.control_air_c,
            snapshot.filtered_temperature_c,
            "--" if env.monitor_air_c is None else f"{env.monitor_air_c:.4f}",
            "--" if env.ground_board_c is None else f"{env.ground_board_c:.4f}",
            "--" if env.spare_c is None else f"{env.spare_c:.4f}",
            "--" if env.humidity_rh is None else f"{env.humidity_rh:.1f}",
            snapshot.setpoint_c,
            snapshot.terms.commanded_current_a,
            "--" if current is None else f"{current:.4f}",
            "--" if power is None else f"{power:.3f}",
            ripple,
            fan,
            snapshot.status,
            warning_text,
        )

    def show_fault(self, message: str) -> None:
        LOG.error("DISPLAY FAULT: %s", message)

    def close(self) -> None:
        return


class Lcd20x4Display:
    HEARTBEAT = ("|", "/", "-", "\\")

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
        self._page_period_s = max(1.0, cfg.lcd_page_period_s)
        self._started = time.monotonic()
        self._heartbeat_index = 0
        self._lcd.clear()

    def _line(self, row: int, text: str) -> None:
        if row >= self._rows:
            return
        self._lcd.cursor_pos = (row, 0)
        self._lcd.write_string(text[: self._cols].ljust(self._cols))

    @staticmethod
    def _fmt_temp(value: Optional[float]) -> str:
        return "--.--" if value is None else f"{value:5.2f}"

    def update(self, snapshot: StatusSnapshot) -> None:
        env = snapshot.environment
        rb = snapshot.readback
        imeas = rb.current_a
        power = rb.power_w
        heartbeat = self.HEARTBEAT[self._heartbeat_index % len(self.HEARTBEAT)]
        self._heartbeat_index += 1
        page = int((time.monotonic() - self._started) / self._page_period_s) % 2

        # A changing final character is a local heartbeat showing the process is
        # still updating even when all measured values have settled.
        self._line(
            0,
            f"T{snapshot.filtered_temperature_c:6.3f} SP{snapshot.setpoint_c:5.2f} {heartbeat}",
        )

        if page == 0:
            current_text = (
                f"{imeas:.3f}" if imeas is not None else f"{snapshot.terms.commanded_current_a:.3f}"
            )
            power_text = (
                f"{power:.2f}" if power is not None else f"{snapshot.terms.commanded_power_w:.2f}"
            )
            self._line(1, f"I {current_text}A P {power_text}W")
            self._line(
                2,
                f"A2{self._fmt_temp(env.monitor_air_c)} B{self._fmt_temp(env.ground_board_c)}",
            )
            rh = "--" if env.humidity_rh is None else f"{env.humidity_rh:.0f}%"
            fan = (
                "OFF"
                if snapshot.fan_spinning is None
                else ("OK" if snapshot.fan_spinning else "FAIL")
            )
            state = "WARN" if snapshot.warnings else snapshot.status
            self._line(3, f"RH{rh} F{fan} {state}")
        else:
            ripple = "--" if snapshot.ripple_pp_c is None else f"{snapshot.ripple_pp_c:.3f}"
            self._line(1, f"Spare {self._fmt_temp(env.spare_c)} C")
            self._line(2, f"Ripple {ripple} C")
            # External slow-controls protocol is intentionally not selected yet.
            sc = (
                "N/A"
                if snapshot.slow_controls_connected is None
                else ("OK" if snapshot.slow_controls_connected else "DOWN")
            )
            warn_count = len(snapshot.warnings)
            self._line(3, f"SC {sc} Warn {warn_count}")

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

        i_w = self.cfg.ki_w_per_c_s * self.integral_c_s
        unsaturated = self.cfg.power_bias_w + p_w + i_w + d_w
        saturated = clamp(unsaturated, 0.0, self.cfg.max_power_w)

        # Conditional integration prevents wind-up at output limits.
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

        maximum_change = max(0.0, self.cfg.current_slew_a_per_s) * dt
        current = clamp(
            current,
            max(0.0, self.last_current_a - maximum_change),
            self.last_current_a + maximum_change,
        )
        self.last_current_a = current

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
        "control_air_temperature_c",
        "filtered_control_temperature_c",
        "monitor_air_temperature_c",
        "ground_board_temperature_c",
        "spare_temperature_c",
        "relative_humidity_percent",
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
        "fan_spinning",
        "sensor_faults",
        "warnings",
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

    @staticmethod
    def _number(value: Optional[float]) -> str:
        return "" if value is None else f"{value:.6f}"

    def write(self, snapshot: StatusSnapshot) -> None:
        rb = snapshot.readback
        terms = snapshot.terms
        env = snapshot.environment
        self._writer.writerow(
            [
                snapshot.timestamp.isoformat(),
                f"{env.control_air_c:.6f}",
                f"{snapshot.filtered_temperature_c:.6f}",
                self._number(env.monitor_air_c),
                self._number(env.ground_board_c),
                self._number(env.spare_c),
                self._number(env.humidity_rh),
                f"{snapshot.setpoint_c:.6f}",
                f"{terms.error_c:.6f}",
                f"{terms.p_w:.6f}",
                f"{terms.i_w:.6f}",
                f"{terms.d_w:.6f}",
                f"{terms.commanded_power_w:.6f}",
                f"{terms.commanded_current_a:.6f}",
                self._number(rb.current_a),
                self._number(rb.voltage_v),
                self._number(rb.power_w),
                self._number(snapshot.ripple_pp_c),
                "" if snapshot.fan_spinning is None else str(snapshot.fan_spinning),
                "; ".join(f"{k}:{v}" for k, v in env.sensor_faults.items()),
                "; ".join(snapshot.warnings),
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
        sensors: SensorSuite,
        actuator: CurrentActuator,
        fan: Fan,
        display: Display,
    ):
        self.cfg = cfg
        self.sensors = sensors
        self.actuator = actuator
        self.fan = fan
        self.display = display
        self.pid = PowerPid(cfg.control)
        self.csv = CsvLogger(cfg.logging.csv_path)
        self._stop = False
        self._fault_latched = False
        self._valid_samples = 0
        self._ripple_samples: Deque[tuple[float, float]] = deque()
        self._last_loop_time = time.monotonic()
        self._closed = False

        atexit.register(self.close)
        signal.signal(signal.SIGTERM, self._signal_stop)
        signal.signal(signal.SIGINT, self._signal_stop)

    def _signal_stop(self, signum: int, _frame: Any) -> None:
        LOG.warning("Received signal %s; shutting down heater", signum)
        self._stop = True

    def _validate_temperature(self, name: str, temperature_c: float) -> None:
        c = self.cfg.control
        if not finite(temperature_c):
            raise RuntimeError(f"{name} temperature is non-finite")
        if not c.minimum_valid_temperature_c <= temperature_c <= c.maximum_valid_temperature_c:
            raise RuntimeError(
                f"{name} temperature {temperature_c:.3f} C is outside valid range"
            )
        if temperature_c >= c.overtemperature_c:
            raise RuntimeError(
                f"over-temperature at {name}: {temperature_c:.3f} C >= "
                f"{c.overtemperature_c:.3f} C"
            )

    def _validate_environment(self, env: EnvironmentReadings) -> list[str]:
        c = self.cfg.control
        self._validate_temperature("control_air", env.control_air_c)
        warnings: list[str] = []

        monitor_values = {
            "monitor_air": env.monitor_air_c,
            "ground_board": env.ground_board_c,
            "spare": env.spare_c,
        }
        for name, value in monitor_values.items():
            if value is None:
                continue
            if not finite(value):
                warnings.append(f"{name} non-finite")
                continue
            if not c.minimum_valid_temperature_c <= value <= c.maximum_valid_temperature_c:
                warnings.append(f"{name} outside valid range")
                continue
            if value >= c.overtemperature_c:
                if c.trip_on_monitor_overtemperature:
                    raise RuntimeError(
                        f"over-temperature at {name}: {value:.3f} C >= "
                        f"{c.overtemperature_c:.3f} C"
                    )
                warnings.append(f"{name} over-temperature")

        if env.monitor_air_c is not None:
            delta = abs(env.control_air_c - env.monitor_air_c)
            if delta > c.air_sensor_disagreement_warning_c:
                warnings.append(f"air PT100 disagreement {delta:.3f} C")

        if env.humidity_rh is not None and env.humidity_rh > c.humidity_warning_rh:
            warnings.append(f"humidity {env.humidity_rh:.1f}% RH")

        for name, text in env.sensor_faults.items():
            warnings.append(f"{name} fault")
            LOG.warning("Sensor fault %s: %s", name, text)

        return warnings

    def _update_ripple(self, now: float, temperature_c: float) -> Optional[float]:
        window = self.cfg.control.ripple_window_s
        self._ripple_samples.append((now, temperature_c))
        while self._ripple_samples and now - self._ripple_samples[0][0] > window:
            self._ripple_samples.popleft()
        if len(self._ripple_samples) < 2:
            return None
        values = [sample[1] for sample in self._ripple_samples]
        return max(values) - min(values)

    def _status(
        self,
        terms: ControllerTerms,
        ripple: Optional[float],
        warnings: list[str],
    ) -> str:
        c = self.cfg.control
        if self._valid_samples < c.startup_valid_samples:
            return "START"
        if warnings:
            return "WARN"
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
        self.fan.start()

        while not self._stop and not self._fault_latched:
            loop_started = time.monotonic()
            dt = max(1e-6, loop_started - self._last_loop_time)
            self._last_loop_time = loop_started

            try:
                sensor_started = time.monotonic()
                env = self.sensors.read_environment()
                sensor_elapsed = time.monotonic() - sensor_started
                if sensor_elapsed > c.sensor_timeout_s:
                    raise RuntimeError(
                        f"sensor-suite read exceeded timeout: {sensor_elapsed:.2f} s"
                    )
                warnings = self._validate_environment(env)
                self._valid_samples += 1

                fan_spinning = self.fan.spinning()
                if self.cfg.hardware.use_fan:
                    if fan_spinning is False:
                        if self.cfg.hardware.fan_required:
                            raise RuntimeError("fan tachometer indicates fan is not spinning")
                        warnings.append("fan not spinning")
                    elif fan_spinning is None and self.cfg.hardware.fan_tach_gpio < 0:
                        warnings.append("fan tachometer not configured")

                terms = self.pid.update(env.control_air_c, dt)

                # Keep the heater disabled until several consecutive valid
                # control PT100 readings have been received after startup.
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
                ripple = self._update_ripple(loop_started, env.control_air_c)
                status = self._status(terms, ripple, warnings)
                snapshot = StatusSnapshot(
                    timestamp=datetime.now(timezone.utc),
                    environment=env,
                    filtered_temperature_c=filtered,
                    setpoint_c=c.setpoint_c,
                    terms=terms,
                    readback=readback,
                    ripple_pp_c=ripple,
                    status=status,
                    warnings=warnings,
                    fan_spinning=fan_spinning,
                    slow_controls_connected=None,
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
            self.fan.close()
        except Exception:
            LOG.exception("Failed to close fan")
        try:
            self.sensors.close()
        except Exception:
            LOG.exception("Failed to close sensor suite")
        try:
            self.display.close()
        except Exception:
            LOG.exception("Failed to close display")
        try:
            self.csv.close()
        except Exception:
            LOG.exception("Failed to close CSV log")


def build_hardware(cfg: AppConfig) -> tuple[SensorSuite, CurrentActuator, Fan]:
    mode = cfg.hardware.mode.strip().lower()
    if mode == "simulate":
        plant = SimulatedPlant(cfg)
        return plant, plant, NullFan()

    sensors: SensorSuite = Max31865SensorSuite(cfg)
    if mode == "dac":
        actuator: CurrentActuator = DacCurrentActuator(cfg.hardware)
    elif mode == "scpi":
        actuator = ScpiCurrentActuator(cfg.hardware)
    else:
        raise ValueError("hardware.mode must be simulate, dac, or scpi")

    fan: Fan = FixedSpeedFan(cfg.hardware) if cfg.hardware.use_fan else NullFan()
    return sensors, actuator, fan


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

    sensors, actuator, fan = build_hardware(cfg)
    display = build_display(cfg)
    controller = StandaloneTemperatureController(cfg, sensors, actuator, fan, display)
    controller.run()
    return 1 if controller._fault_latched else 0


if __name__ == "__main__":
    sys.exit(main())
