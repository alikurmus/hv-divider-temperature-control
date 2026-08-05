
from __future__ import annotations

import atexit
import csv
import datetime
import logging
import queue
import threading
import time
from typing import Any, Optional, Tuple

from dripline.core import Service, ThrowReply

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp x to the inclusive range [lo, hi]."""
    return lo if x < lo else hi if x > hi else x


def pt100_resistance_to_kelvin(resistance: float) -> float:
    """
    Convert PT100 resistance (ohms) to temperature (Kelvin).

    - For the RTD01 cryogenic region (R ~= 14-15 ohm), use the custom polynomial.
    - Otherwise, use the standard IEC 60751 quadratic branch for 0-850 C.
    """
    if 13.0 <= resistance <= 17.0:
        a = 0.059524
        b = 0.178571
        c = 47.628423
        return a * resistance**2 + b * resistance + c

    R0 = 100.0
    A = 3.9083e-3
    B = -5.775e-7

    cq = 1.0 - (resistance / R0)
    disc = A * A - 4.0 * B * cq
    if disc < 0:
        logger.error("PT100 conversion: negative discriminant for R=%.3f ohm", resistance)
        return float("nan")

    sqrt_disc = disc ** 0.5
    t1 = (-A + sqrt_disc) / (2.0 * B)
    t2 = (-A - sqrt_disc) / (2.0 * B)
    candidates = [t for t in (t1, t2) if -200.0 <= t <= 850.0]
    if not candidates:
        logger.error("PT100 conversion: no physical solution for R=%.3f ohm", resistance)
        return float("nan")

    return candidates[0] + 273.15


class PidController(Service):
    """
    Slow-controls PID service for a heater regulating a thermally leaky box/room.

    The intended plant model is the thermal-loss model

        dT/dt = heater_power - k_loss * (T - T_env),

    so this controller should be thought of as:

    - process variable (PV): box temperature
    - setpoint (SP): desired box temperature
    - output (u): heater command sent to the slow-controls output endpoint

    The public interface from the previous integrated controller is preserved:
    - __get_current()
    - __validate_status()
    - this_consume(message, method)
    - process_new_value(value, timestamp)
    - set_current(value)
    - target_value property
    """

    def __init__(
        self,
        input_channel: str,
        output_channel: str,
        check_channel: Optional[str] = None,
        status_channel: Optional[str] = None,
        voltage_channel: Optional[str] = None,
        payload_field: str = "value_cal",
        target_value: float = 35.0,
        proportional: float = 0.5,
        integral: float = 0.02,
        differential: float = 0.0,
        maximum_out: float = 1.0,
        minimum_out: float = 0.0,
        delta_out_min: float = 0.001,
        minimum_elapsed_time: float = 5.0,
        poll_period_s: float = 5.0,
        integral_limit: Optional[float] = None,
        derivative_smoothing: float = 0.85,
        convert_pt100: bool = False,
        startup_enable_value: Optional[float] = 1.0,
        startup_voltage: Optional[float] = None,
        verify_tolerance: Optional[float] = None,
        max_settle_wait_s: float = 2.0,
        heater_bias: float = 0.0,
        loss_compensation_gain: float = 0.0,
        ambient_value: Optional[float] = None,
        log_path: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        # Channels
        self._input_channel = input_channel
        self._set_channel = output_channel
        self._check_channel = check_channel
        self._status_channel = status_channel
        self._voltage_channel = voltage_channel
        self.payload_field = payload_field

        # Setpoint / gains
        self._target_value = float(target_value)
        self.Kproportional = float(proportional)
        self.Kintegral = float(integral)
        self.Kdifferential = float(differential)

        # Output shaping
        self.max_output = float(maximum_out)
        self.min_output = float(minimum_out)
        self.min_output_change = float(delta_out_min)
        self.verify_tolerance = verify_tolerance
        self.max_settle_wait_s = float(max_settle_wait_s)

        # Timing
        self.minimum_elapsed_time = max(0.0, float(minimum_elapsed_time))
        self._poll_period_s = max(0.1, float(poll_period_s))

        # Thermal-model-inspired helpers
        self.heater_bias = float(heater_bias)
        self.loss_compensation_gain = float(loss_compensation_gain)
        self.ambient_value = ambient_value

        # Sensor handling
        self._convert_pt100 = bool(convert_pt100)

        # PID state
        self._integral = 0.0
        self._int_limit = None if integral_limit is None else abs(float(integral_limit))
        self._alpha_d = clamp(float(derivative_smoothing), 0.0, 1.0)
        self._ema_dpvdt = 0.0
        self._last_data = {"value": None, "time": None}
        self._force_reprocess = False

        # Output state
        self._old_output = 0.0

        # CSV logging
        self._log_lock = threading.Lock()
        self._log_data = []
        self._log_autoflush_every = 10
        if log_path is None:
            timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            self._log_filename = f"/app/logs/pid_log_{timestamp}.csv"
        else:
            self._log_filename = log_path
        self._log_header_written = False
        atexit.register(self._flush_log_to_csv)

        # Initialize hardware into a known state
        if self._status_channel is not None and startup_enable_value is not None:
            logger.info("Setting %s to %s", self._status_channel, startup_enable_value)
            self.set(self._status_channel, startup_enable_value)

        if self._voltage_channel is not None and startup_voltage is not None:
            logger.info("Setting %s to %s", self._voltage_channel, startup_voltage)
            self.set(self._voltage_channel, startup_voltage)

        self.__validate_status()

        if self._check_channel is not None:
            try:
                self._old_output = self.__get_current()
            except Exception as ex:
                logger.warning("Could not read initial actuator output: %s", ex)
                self._old_output = 0.0

        logger.info(
            "Thermal PID ready: SP=%s Kp=%s Ki=%s Kd=%s output_range=[%s, %s] poll=%ss",
            self._target_value,
            self.Kproportional,
            self.Kintegral,
            self.Kdifferential,
            self.min_output,
            self.max_output,
            self._poll_period_s,
        )

        t = threading.Thread(target=self._poll_sensor_loop, name="pid-poll", daemon=True)
        t.start()

    # ------------------------------------------------------------------
    # Public interface preserved
    # ------------------------------------------------------------------

    @property
    def target_value(self) -> float:
        return self._target_value

    @target_value.setter
    def target_value(self, value: float) -> None:
        logger.info("Changing target_value from %s to %s", self._target_value, value)
        self._target_value = float(value)
        self._integral = 0.0
        self._ema_dpvdt = 0.0
        self._force_reprocess = True

    def __validate_status(self) -> None:
        """
        If a status channel is configured, require a truthy enabled state.
        """
        if self._status_channel is None:
            return

        resp = self.get(self._status_channel)
        value = resp.get(self.payload_field)
        if not value:
            raise ThrowReply(
                "resource_error",
                f"{self._status_channel} returned disabled/invalid state: {value}",
            )

    def __get_current(self) -> float:
        """
        Preserve legacy name: returns actuator readback.
        """
        if self._check_channel is None:
            return float(self._old_output)

        resp = self._get_with_deadline(self._check_channel, timeout_s=1.0)
        if not resp:
            raise ThrowReply("service_error_invalid_value", "actuator readback timeout/no reply")

        value = resp.get(self.payload_field)
        try:
            return float(value)
        except (TypeError, ValueError) as ex:
            raise ThrowReply("service_error_invalid_value", f"readback not floatable: {value}") from ex

    def set_current(self, value: float) -> None:
        """
        Preserve legacy method name: send heater command to output_channel.
        """
        logger.info("Setting actuator command to %.6f", value)
        ok, reply = self._set_with_deadline(self._set_channel, float(value), timeout_s=1.0)
        if not ok:
            logger.warning("set_current: no reply or failure")
        else:
            logger.debug("set_current reply: %s", reply)

    def this_consume(self, message: Any, method: Optional[str] = None) -> None:
        """
        Optional message-driven entry point if slow controls delivers updates
        through subscriptions instead of polling.
        """
        try:
            payload = getattr(message, "payload", None) or {}
            raw_value = payload.get(self.payload_field)
            if raw_value is None:
                return

            value = float(raw_value)
            if self._convert_pt100:
                value = pt100_resistance_to_kelvin(value)

            timestamp = self._parse_timestamp(payload)
            self.process_new_value(value=value, timestamp=timestamp)
        except Exception as ex:
            logger.exception("this_consume failed: %s", ex)

    def process_new_value(self, value: float, timestamp: datetime.datetime) -> None:
        """
        Execute one PID update for the thermal-loss box model.

        Control convention:
            error = SP - PV

        Output law:
            u = heater_bias
                + loss_compensation_gain * max(SP - ambient, 0)
                + Kp * error
                + Ki * integral(error dt)
                - Kd * d(PV)/dt

        The derivative acts on the measurement to reduce setpoint kick.
        """
        last_time = self._last_data["time"]
        last_value = self._last_data["value"]

        if last_time is None:
            self._last_data = {"value": value, "time": timestamp}
            logger.info("Initialized thermal PID with first sample PV=%.4f", value)
            return

        dt = (timestamp - last_time).total_seconds()
        if dt <= 0:
            dt = max(self.minimum_elapsed_time, 1e-6)

        if dt < self.minimum_elapsed_time and not self._force_reprocess:
            logger.debug("Skipping update because dt=%.3fs < minimum_elapsed_time", dt)
            return

        self._force_reprocess = False

        error = self._target_value - value

        # Integral with explicit clamp to prevent windup.
        self._integral += error * dt
        if self._int_limit is not None:
            self._integral = clamp(self._integral, -self._int_limit, self._int_limit)

        # Derivative on measurement with EMA smoothing.
        if last_value is None:
            d_pv_dt = 0.0
        else:
            raw_d = (value - last_value) / dt
            self._ema_dpvdt = self._alpha_d * self._ema_dpvdt + (1.0 - self._alpha_d) * raw_d
            d_pv_dt = self._ema_dpvdt

        self._last_data = {"value": value, "time": timestamp}

        feedforward = self.heater_bias
        if self.ambient_value is not None and self.loss_compensation_gain != 0.0:
            feedforward += self.loss_compensation_gain * max(self._target_value - self.ambient_value, 0.0)

        p_term = self.Kproportional * error
        i_term = self.Kintegral * self._integral
        d_term = -self.Kdifferential * d_pv_dt

        new_output = feedforward + p_term + i_term + d_term
        unsat_output = new_output
        new_output = clamp(new_output, self.min_output, self.max_output)

        # Back-calculation anti-windup if saturation occurs.
        if self.Kintegral > 0.0 and new_output != unsat_output:
            self._integral += (new_output - unsat_output) / self.Kintegral
            if self._int_limit is not None:
                self._integral = clamp(self._integral, -self._int_limit, self._int_limit)
            i_term = self.Kintegral * self._integral

        if abs(new_output - self._old_output) < self.min_output_change:
            self._log_append(timestamp, value, self._target_value, self._old_output, p_term, i_term, d_term)
            return

        self.set_current(new_output)
        self._verify_after_set(new_output)
        self._old_output = new_output

        self._log_append(timestamp, value, self._target_value, new_output, p_term, i_term, d_term)
        logger.info(
            "PV=%.4f SP=%.4f e=%.4f dt=%.3f u=%.6f [P=%.4f I=%.4f D=%.4f FF=%.4f]",
            value,
            self._target_value,
            error,
            dt,
            new_output,
            p_term,
            i_term,
            d_term,
            feedforward,
        )

    # ------------------------------------------------------------------
    # Polling / I/O helpers
    # ------------------------------------------------------------------

    def _poll_sensor_loop(self) -> None:
        """
        Poll the temperature endpoint at a fixed cadence.

        Unlike the earlier integrated version, this loop always sleeps enough
        to enforce the requested poll period even after a successful cycle.
        """
        while True:
            cycle_start = time.monotonic()
            try:
                timeout_s = max(1.0, 0.8 * self._poll_period_s + 0.2)
                resp = self._get_with_deadline(self._input_channel, timeout_s=timeout_s)
                if resp:
                    this_value = resp.get(self.payload_field)
                    if this_value is not None:
                        value = float(this_value)
                        if self._convert_pt100:
                            value = pt100_resistance_to_kelvin(value)
                        timestamp = self._parse_timestamp(resp)
                        self.process_new_value(value=value, timestamp=timestamp)
            except Exception as ex:
                logger.exception("[PV poll] failure: %s", ex)

            elapsed = time.monotonic() - cycle_start
            time.sleep(max(0.0, self._poll_period_s - elapsed))

    def _parse_timestamp(self, payload: dict) -> datetime.datetime:
        ts_raw = payload.get("timestamp") or payload.get("time") or payload.get("ts")
        if ts_raw:
            for fmt in ("%d/%m/%y %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.datetime.strptime(ts_raw, fmt)
                except Exception:
                    pass
        return datetime.datetime.utcnow()

    def _get_with_deadline(self, channel: str, timeout_s: float = 1.0) -> Optional[dict]:
        q: "queue.Queue[Tuple[bool, Any]]" = queue.Queue(maxsize=1)

        def _worker() -> None:
            try:
                q.put((True, self.get(channel)))
            except Exception as ex:
                q.put((False, ex))

        t = threading.Thread(target=_worker, name=f"get:{channel}", daemon=True)
        t.start()
        try:
            ok, val = q.get(timeout=timeout_s)
            if ok:
                return val
            logger.warning("GET %s failed: %s", channel, val)
            return None
        except queue.Empty:
            logger.warning("GET %s timed out after %.2fs", channel, timeout_s)
            return None
        finally:
            t.join(timeout=0.1)

    def _set_with_deadline(self, channel: str, value: float, timeout_s: float = 1.0) -> Tuple[bool, Any]:
        q: "queue.Queue[Tuple[bool, Any]]" = queue.Queue(maxsize=1)

        def _worker() -> None:
            try:
                q.put((True, self.set(channel, value)))
            except Exception as ex:
                q.put((False, ex))

        t = threading.Thread(target=_worker, name=f"set:{channel}", daemon=True)
        t.start()
        try:
            ok, val = q.get(timeout=timeout_s)
            if ok:
                return True, val
            logger.warning("SET %s failed: %s", channel, val)
            return False, val
        except queue.Empty:
            logger.warning("SET %s timed out after %.2fs", channel, timeout_s)
            return False, None
        finally:
            t.join(timeout=0.1)

    def _verify_after_set(self, requested_output: float) -> None:
        """
        Optional bounded readback check after writing a new heater command.
        """
        if self._check_channel is None or self.verify_tolerance is None:
            return

        deadline = time.monotonic() + self.max_settle_wait_s
        while time.monotonic() < deadline:
            try:
                actual = self.__get_current()
                if abs(actual - requested_output) <= self.verify_tolerance:
                    return
            except Exception:
                pass
            time.sleep(0.1)

        logger.warning(
            "Readback did not settle within tolerance: requested=%.6f tolerance=%.6f",
            requested_output,
            self.verify_tolerance,
        )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_append(
        self,
        timestamp: datetime.datetime,
        pv: float,
        sp: float,
        u: float,
        p_term: float,
        i_term: float,
        d_term: float,
    ) -> None:
        row = (
            timestamp.isoformat(),
            float(pv),
            float(sp),
            float(u),
            float(p_term),
            float(i_term),
            float(d_term),
        )

        should_flush = False
        with self._log_lock:
            self._log_data.append(row)
            if len(self._log_data) >= self._log_autoflush_every:
                should_flush = True

        if should_flush:
            self._flush_log_to_csv()

    def _flush_log_to_csv(self) -> None:
        with self._log_lock:
            if not self._log_data:
                return
            rows = self._log_data
            self._log_data = []

        try:
            with open(self._log_filename, "a", newline="") as f:
                writer = csv.writer(f)
                if not self._log_header_written:
                    writer.writerow(["time", "PV", "SP", "u", "P_term", "I_term", "D_term"])
                    self._log_header_written = True
                writer.writerows(rows)
        except Exception as ex:
            logger.exception("Failed flushing CSV log: %s", ex)
