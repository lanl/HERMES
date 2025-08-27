"""
TPX3 Zaber Controller Utilities
===============================

A small helper module to work with a Zaber X‑Series controller
(e.g., X‑MCC4) from Python. Focus areas:

- Robust port discovery across Linux/macOS
- Clean connection lifecycle (context manager friendly)
- Convenient analog / digital I/O helpers
- Device selection by address/index and graceful compatibility with multiple zaber‑motion versions
- Helpful debug logging and actionable error messages (permissions, busy port)

Dependencies (no auto-installation here):
    - zaber-motion (https://pypi.org/project/zaber-motion/)
    - pyserial (https://pypi.org/project/pyserial/)

Example
-------
```python
from tpx3Zaber import ZaberController

# Find a port, open a connection, set AO1 to 2.5 V
with ZaberController(debug=True) as z:
    z.open()  # auto-discover port and baud
    z.select_device()  # pick the first detected device
    z.set_analog_output(1, 2.50)
    print("AO1:", z.get_analog_output(1))
```

Design Notes
------------
- We separate **discovery** from **control** to avoid keeping stale `Device`
  objects after a probing connection is closed.
- We avoid passing `timeout=` to `Connection.open_serial_port(...)` because
  some versions of `zaber-motion` do not accept that keyword.
- We expose clear exceptions and structured results to make integration into a
  DAQ pipeline straightforward.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple, Dict, Any
import sys
import time
import contextlib
from serial.tools import list_ports
from zaber_motion.ascii import Connection # type: ignore[reportMissingImports]



# --------------------------------------------------------------------------------------
# Utility dataclasses & exceptions
# --------------------------------------------------------------------------------------

@dataclass
class PortProbe:
    device: str
    manufacturer: Optional[str]
    product: Optional[str]
    vid: Optional[int]
    pid: Optional[int]

    def looks_like_zaber(self) -> bool:
        meta = f"{self.manufacturer or ''} {self.product or ''}".lower()
        return "zaber" in meta


class ZaberError(RuntimeError):
    """Base error for this module."""


class ZaberNotFound(ZaberError):
    """Raised when no Zaber ASCII devices respond on any candidate port."""


class ZaberPermissionHint(ZaberError):
    """Augmented error with OS-specific hints about serial permissions."""


# --------------------------------------------------------------------------------------
# Platform helpers
# --------------------------------------------------------------------------------------

def _default_port_prefixes() -> Tuple[str, ...]:
    """Return sensible device-name prefixes for the current OS.

    Linux:  /dev/ttyACM*, /dev/ttyUSB*
    macOS:  /dev/tty.usbmodem*, /dev/tty.usbserial*
    Windows: COM (scanning is different; we still filter by 'COM')
    """
    if sys.platform.startswith("linux"):
        return ("/dev/ttyACM", "/dev/ttyUSB")
    if sys.platform == "darwin":
        return ("/dev/tty.usbmodem", "/dev/tty.usbserial")
    # Windows & others
    return ("COM",)


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


# --------------------------------------------------------------------------------------
# Core controller class
# --------------------------------------------------------------------------------------

class ZaberController:
    """High-level wrapper around zaber-motion for IO-centric workflows.

    Parameters
    ----------
    port_prefixes:
        Iterable of device-name prefixes to consider during discovery. If None,
        platform-appropriate defaults are used.
    baud_candidates:
        Baud rates to try during discovery. X-Series default is 115200.
    debug:
        If True, prints verbose discovery/connection logs to stdout.

    Notes
    -----
    - Use as a context manager or call `open()`/`close()` explicitly.
    - After `open()`, call `select_device()` to bind a `Device` to this wrapper.
    """

    def __init__(
        self,
        port_prefixes: Optional[Iterable[str]] = None,
        baud_candidates: Iterable[int] = (115200, 9600),
        debug: bool = False,
    ) -> None:
        self.port_prefixes = tuple(port_prefixes) if port_prefixes else _default_port_prefixes()
        self.baud_candidates = tuple(baud_candidates)
        self.debug = debug
        self._conn: Optional[Connection] = None
        self._port: Optional[str] = None
        self._baud: Optional[int] = None
        self._device = None  # type: ignore[attr-defined]

    # ----- context manager --------------------------------------------------
    def __enter__(self) -> "ZaberController":  # pragma: no cover
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover
        self.close()

    # ----- discovery --------------------------------------------------------
    @staticmethod
    def _probe_ports(prefixes: Tuple[str, ...]) -> List[PortProbe]:
        ports = list(list_ports.comports())
        results: List[PortProbe] = []
        for p in ports:
            dev = getattr(p, "device", None)
            if not dev:
                continue
            if not any(dev.startswith(pref) for pref in prefixes):
                continue
            results.append(
                PortProbe(
                    device=dev,
                    manufacturer=getattr(p, "manufacturer", None),
                    product=getattr(p, "product", None),
                    vid=getattr(p, "vid", None),
                    pid=getattr(p, "pid", None),
                )
            )
        # Prefer Zaber-looking ports first, then lexical order for stability
        results.sort(key=lambda r: (0 if r.looks_like_zaber() else 1, r.device))
        return results

    def discover(self) -> Tuple[str, int, Optional[int]]:
        """Probe candidate ports/bauds and return (port, baud, address).

        The probing connection is closed before returning. `address` may be
        None if the `Device` object doesn't expose an address accessor in your
        zaber-motion version; we only use it for a fast re-bind later.
        """
        candidates = self._probe_ports(self.port_prefixes)
        if self.debug:
            print("== USB serial candidates ==")
            if not candidates:
                print("(none)")
            for c in candidates:
                print(
                    f"- {c.device} | manu={c.manufacturer} product={c.product} vid={c.vid} pid={c.pid}"
                )

        last_error: Optional[str] = None
        for c in candidates:
            for baud in self.baud_candidates:
                try:
                    if self.debug:
                        print(f"Trying {c.device} @ {baud} ...", end="", flush=True)
                    with Connection.open_serial_port(c.device, baud_rate=baud) as conn:
                        devices = conn.detect_devices()
                        if devices:
                            # Get a stable address if available
                            addr = None
                            d0 = devices[0]
                            for cand in ("device_address", "address", "get_address"):
                                if hasattr(d0, cand):
                                    v = getattr(d0, cand)
                                    addr = v() if callable(v) else v
                                    break
                            if self.debug:
                                print(" success.", f" address={addr}" if addr is not None else "")
                            return c.device, baud, addr
                    if self.debug:
                        print(" no devices.")
                except Exception as e:  # capture and continue
                    last_error = str(e)
                    if self.debug:
                        print(f" error: {e}")

        # Prepare informative error with platform hints
        hint = []
        if _is_linux():
            hint.append(
                "On Linux, ensure your user is in the 'dialout' group and re-login: "
                "sudo usermod -a -G dialout $USER"
            )
        hint.append("Close any other app using the port (serial monitor, GUI, etc.)")
        msg = "No Zaber ASCII devices responded on candidate ports."
        if last_error:
            msg += f" Last error: {last_error}"
        if hint:
            msg += "\nHints: " + "; ".join(hint)
        raise ZaberNotFound(msg)

    # ----- connection -------------------------------------------------------
    def open(self, port: Optional[str] = None, baud: Optional[int] = None) -> None:
        """Open a persistent connection.

        If `port`/`baud` are omitted, runs discovery first.
        """
        if self._conn is not None:
            return  # already open

        if port is None or baud is None:
            port, baud, addr = self.discover()
            self._port, self._baud = port, baud
        else:
            self._port, self._baud = port, baud
            addr = None

        # Open the connection we will keep for the session
        try:
            self._conn = Connection.open_serial_port(self._port, baud_rate=self._baud)
        except Exception as e:
            # Permissions help on Linux
            if _is_linux():
                raise ZaberPermissionHint(
                    f"Failed to open {self._port}: {e}\n"
                    "If you see 'Permission denied', add your user to 'dialout' and re-login:\n"
                    "  sudo usermod -a -G dialout $USER"
                ) from e
            raise

        if self.debug:
            print(f"Opened Zaber connection on {self._port} @ {self._baud}")

        # Try to bind a default device right away if we could learn an address
        with contextlib.suppress(Exception):
            if addr is not None:
                self.select_device(address=addr)

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None
                self._device = None
                if self.debug:
                    print("Closed Zaber connection")

    # ----- device selection -------------------------------------------------
    def list_devices(self) -> List[Any]:
        """Detect and return the device objects for the active connection."""
        if self._conn is None:
            raise ZaberError("Connection not open. Call open() first.")
        return self._conn.detect_devices()

    def select_device(self, address: Optional[int] = None, index: int = 0) -> Any:
        """Bind a device to this controller.

        Parameters
        ----------
        address:
            Numeric device address to bind. If None, the `index`-th detected
            device is used.
        index:
            Index in the `detect_devices()` list used when address is None.
        """
        if self._conn is None:
            raise ZaberError("Connection not open. Call open() first.")

        dev = None
        if address is not None and hasattr(self._conn, "get_device"):
            with contextlib.suppress(Exception):
                dev = self._conn.get_device(address)  # type: ignore[attr-defined]
        if dev is None:
            devices = self._conn.detect_devices()
            if not devices:
                raise ZaberNotFound("No devices detected on the open connection.")
            try:
                dev = devices[index]
            except IndexError:  # pragma: no cover
                raise ZaberError(f"Device index {index} out of range (found {len(devices)}).")

        self._device = dev
        if self.debug:
            desc = self._describe_device(dev)
            print(f"Selected device: {desc}")
        return dev

    # ----- IO helpers -------------------------------------------------------
    def _require_device(self) -> Any:
        if self._conn is None:
            raise ZaberError("Connection not open. Call open() first.")
        if self._device is None:
            raise ZaberError("No device selected. Call select_device() first.")
        return self._device

    # Analog Output ----------------------------------------------------------
    def set_analog_output(self, channel: int, volts: float) -> None:
        """Set a single analog output in Volts.

        Notes
        -----
        - Channels are typically **1-based** on X-Series devices.
        - The allowed range is device-specific (often 0–5 V on X‑MCC4).
        """
        dev = self._require_device()
        dev.io.set_analog_output(channel, volts)

    def get_analog_output(self, channel: int) -> Optional[float]:
        """Read back the analog output voltage if supported; else return None."""
        dev = self._require_device()
        with contextlib.suppress(Exception):
            return float(dev.io.get_analog_output(channel))
        return None

    def set_analog_outputs(self, values: Dict[int, float]) -> None:
        """Set multiple AO channels: `values={channel: volts, ...}`"""
        for ch, v in values.items():
            self.set_analog_output(ch, v)

    def ramp_analog_output(
        self,
        channel: int,
        start_v: float,
        stop_v: float,
        duration_s: float,
        steps: int = 50,
        sleep_func=time.sleep,
    ) -> None:
        """Linearly ramp AO from `start_v` to `stop_v` over `duration_s` in `steps`.

        This performs a simple blocking ramp suitable for slow analog changes.
        For tighter timing, consider using your experiment clock to schedule
        `set_analog_output` calls externally.
        """
        if steps <= 0:
            raise ValueError("steps must be > 0")
        if duration_s < 0:
            raise ValueError("duration_s must be >= 0")
        if steps == 1:
            self.set_analog_output(channel, stop_v)
            return

        dt = duration_s / (steps - 1)
        dv = (stop_v - start_v) / (steps - 1)
        v = start_v
        for _ in range(steps):
            self.set_analog_output(channel, v)
            if dt > 0:
                sleep_func(dt)
            v += dv

    # Digital IO -------------------------------------------------------------
    def set_digital_output(self, channel: int, state: bool) -> None:
        dev = self._require_device()
        dev.io.set_digital_output(channel, bool(state))

    def get_digital_output(self, channel: int) -> Optional[bool]:
        dev = self._require_device()
        with contextlib.suppress(Exception):
            return bool(dev.io.get_digital_output(channel))
        return None

    def get_all_digital_outputs(self) -> List[bool]:
        dev = self._require_device()
        with contextlib.suppress(Exception):
            return list(dev.io.get_all_digital_outputs())
        return []

    def get_digital_input(self, channel: int) -> Optional[bool]:
        dev = self._require_device()
        with contextlib.suppress(Exception):
            return bool(dev.io.get_digital_input(channel))
        return None

    def get_all_digital_inputs(self) -> List[bool]:
        dev = self._require_device()
        with contextlib.suppress(Exception):
            return list(dev.io.get_all_digital_inputs())
        return []

    # ----- info / utilities -------------------------------------------------
    @staticmethod
    def _describe_device(dev: Any) -> str:
        # Try multiple attribute names to stay compatible across versions
        parts = []
        for a in ("device_address", "address", "get_address"):
            with contextlib.suppress(Exception):
                v = getattr(dev, a)
                if callable(v):
                    v = v()
                if v is not None:
                    parts.append(f"addr={v}")
                    break
        for a in ("name", "serial_number", "get_name"):
            with contextlib.suppress(Exception):
                v = getattr(dev, a)
                if callable(v):
                    v = v()
                if v:
                    parts.append(str(v))
                    break
        return " ".join(parts) if parts else "device"

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    @property
    def port(self) -> Optional[str]:
        return self._port

    @property
    def baud(self) -> Optional[int]:
        return self._baud


# --------------------------------------------------------------------------------------
# Convenience top-level helpers (optional functional API)
# --------------------------------------------------------------------------------------

def auto_set_analog_output(channel: int, volts: float, debug: bool = False) -> None:
    """One-liner convenience: discover, open, select first device, set AO, close."""
    with ZaberController(debug=debug) as z:
        z.open()
        z.select_device()
        z.set_analog_output(channel, volts)


def discover_all_candidates(port_prefixes: Optional[Iterable[str]] = None) -> List[PortProbe]:
    """Return the list of candidate USB serial devices that match platform prefixes.

    This does *not* attempt to open or talk to the ports; it's useful for
    presenting choices to a user.
    """
    prefixes = tuple(port_prefixes) if port_prefixes else _default_port_prefixes()
    return ZaberController._probe_ports(prefixes)


# --------------------------------------------------------------------------------------
# CLI demo (optional): python tpx3Zaber.py --set-ao 1 2.5 --debug
# --------------------------------------------------------------------------------------
if __name__ == "__main__":  # pragma: no cover
    import argparse

    ap = argparse.ArgumentParser(description="Control Zaber analog/digital IO")
    ap.add_argument("--set-ao", nargs=2, metavar=("CHANNEL", "VOLTS"), help="Set AO channel to volts")
    ap.add_argument("--get-ao", nargs=1, metavar=("CHANNEL",), help="Read AO channel")
    ap.add_argument("--set-do", nargs=2, metavar=("CHANNEL", "STATE"), help="Set DO channel to 0/1")
    ap.add_argument("--get-do", nargs=1, metavar=("CHANNEL",), help="Read DO channel")
    ap.add_argument("--list", action="store_true", help="List detected devices")
    ap.add_argument("--debug", action="store_true")

    args = ap.parse_args()

    z = ZaberController(debug=args.debug)
    try:
        z.open()
        if args.list:
            devs = z.list_devices()
            print("Devices:")
            for d in devs:
                print(" -", z._describe_device(d))

        z.select_device()

        if args.set_ao:
            ch = int(args.set_ao[0]); v = float(args.set_ao[1])
            z.set_analog_output(ch, v)
            print(f"AO{ch} set to {v} V")
        if args.get_ao:
            ch = int(args.get_ao[0])
            v = z.get_analog_output(ch)
            print(f"AO{ch} = {v} V")
        if args.set_do:
            ch = int(args.set_do[0]); state = bool(int(args.set_do[1]))
            z.set_digital_output(ch, state)
            print(f"DO{ch} set to {int(state)}")
        if args.get_do:
            ch = int(args.get_do[0])
            v = z.get_digital_output(ch)
            print(f"DO{ch} = {int(v) if v is not None else 'N/A'}")
    finally:
        z.close()

def set_zaber_ao(volts: float, channel: int, verbose: int = 1):
    """Set Zaber analog output."""
    try:
        with ZaberController(debug=(verbose > 1)) as z:
            z.open()
            z.select_device()
            z.set_analog_output(channel, float(volts))
            if verbose > 0:
                print(f"[INFO] Zaber AO{channel} set to {volts:.3f} V")
    except (ZaberNotFound, ZaberError, Exception) as e:
        if verbose > 0:
            print(f"[WARN] Could not set Zaber AO{channel} to {volts:.3f} V: {e}")
