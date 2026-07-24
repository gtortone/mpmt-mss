#!/usr/bin/env python3
"""
mss_cli.py — Interactive CLI for the mpmt-mss RPC service.

Automatically generates one command per RPC namespace (fpga, sensors,
febmgr) with a subcommand for each method, reading the spec from
NAMESPACE_SPEC in mssclient.py. Adding/changing a method in
NAMESPACE_SPEC (or on the server) is reflected here automatically,
without touching the CLI code.

Requirements:
    pip install cmd2 requests

This file must be run from an environment where the `mpmt_mss` package
is importable (e.g. inside the repo with `uv run python mss_cli.py`, or
after `pip install -e .` from the repo root), because mssclient.py
imports `mpmt_mss.feb.devices` and `mpmt_mss.feb.ledchannel`.

Usage:
    python mss_cli.py --url http://zynq:8000/rpc

Command examples once inside the shell:
    fpga readRegister 1
    sensors read --table
    sensors read --table --count 10 --interval 1
    febmgr getStatus --channel_type PMT --table
    febmgr getPMTVoltage 6
    febmgr setPMTVoltageSet 6 689
    febmgr setLEDChannels 7 1 2 3 --append true
    enable_all
    disable_all -y
    status
    status --channel_type PMT
    pmt_info
    online
    methods
    schema
    raw febmgr.getPMTStatus {"channel": 6} --table
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
import time
import typing
from enum import Enum

try:
    import cmd2
except ImportError:
    sys.exit("Missing package 'cmd2'. Install with: pip install cmd2")

try:
    import mpmt_mss.client.python.mssclient as mssclient
except ImportError:
    sys.exit(
        "Could not import mssclient.py.\n"
        "Run this script from the same folder as mssclient.py, or make "
        "sure src/mpmt_mss is on the PYTHONPATH / the mpmt_mss package "
        "is installed (uv run / pip install -e .)."
    )


# ---------------------------------------------------------------------------
# Introspection of the types declared in NAMESPACE_SPEC, used to build the
# matching argparse arguments automatically.
# ---------------------------------------------------------------------------

def _unwrap_optional(ptype):
    """Optional[X] -> X. Returns ptype unchanged if it isn't an Optional."""
    origin = typing.get_origin(ptype)
    if origin is typing.Union:
        args = [a for a in typing.get_args(ptype) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return ptype


def _is_list_type(ptype):
    origin = typing.get_origin(ptype)
    return origin in (list,)


def _list_elem_type(ptype):
    args = typing.get_args(ptype)
    return args[0] if args else str


def _str2bool(value: str) -> bool:
    if isinstance(value, bool):
        return value
    v = value.strip().lower()
    if v in ("1", "true", "t", "yes", "y", "on"):
        return True
    if v in ("0", "false", "f", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {value!r}")


def _add_param_argument(subparser: argparse.ArgumentParser, name: str, ptype, required: bool):
    """Adds an argument to the subparser matching the type declared in
    NAMESPACE_SPEC (int, float, str, bool, List[T], Enum, Optional[...]).
    """
    real_type = _unwrap_optional(ptype)
    kwargs: dict = {}

    if _is_list_type(real_type):
        elem_type = _list_elem_type(real_type)
        elem_type = elem_type if elem_type in (int, float, str) else str
        kwargs["nargs"] = "+"
        kwargs["type"] = elem_type
        kwargs["metavar"] = f"{name.upper()}..."
    elif inspect.isclass(real_type) and issubclass(real_type, Enum):
        kwargs["choices"] = [e.value for e in real_type]
        kwargs["type"] = str
    elif real_type is bool:
        kwargs["type"] = _str2bool
        kwargs["metavar"] = "true|false"
    elif real_type in (int, float, str):
        kwargs["type"] = real_type
    else:
        # safe fallback for unanticipated types
        kwargs["type"] = str

    if required:
        subparser.add_argument(name, **kwargs)
    else:
        kwargs["default"] = None
        subparser.add_argument(f"--{name}", **kwargs)


def _method_help(python_name: str, params: list, rtype) -> str:
    rtype_name = getattr(rtype, "__name__", str(rtype))
    plist = ", ".join(n for n, _t, _r in params) or "-"
    return f"({plist}) -> {rtype_name}"


# ---------------------------------------------------------------------------
# Plain-text table formatting (no external dependency).
# ---------------------------------------------------------------------------

def _format_table(headers: list, rows: list) -> str:
    str_rows = [["" if v is None else str(v) for v in row] for row in rows]
    widths = [len(str(h)) for h in headers]
    for row in str_rows:
        for i, v in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(v))

    def fmt(vals):
        return "  ".join(str(v).ljust(widths[i]) for i, v in enumerate(vals))

    lines = [fmt(headers), fmt(["-" * w for w in widths])]
    lines += [fmt(row) for row in str_rows]
    return "\n".join(lines)


def _dicts_to_table(dicts: list) -> tuple:
    """Turns a list of dicts (e.g. a getStatus() result) into headers/rows,
    preserving field order and tolerating dicts with different keys.
    """
    headers: list = []
    for d in dicts:
        for k in d.keys():
            if k not in headers:
                headers.append(k)
    rows = [[d.get(h, "") for h in headers] for d in dicts]
    return headers, rows


def _is_reading_item(x) -> bool:
    return isinstance(x, dict) and "label" in x and "value" in x


def _is_value_string_item(x) -> bool:
    return isinstance(x, dict) and "value" in x and "string" in x


def _flatten_result_dict(d: dict) -> dict:
    """Best-effort flattening of a dict result for tabular display.

    Handles the common HouseKeeping.read() shape:
        {"tla2024": [{"label": "+5.0V", "unit": "V", "value": 4.61}, ...], ...}
    turning it into flat, single-value fields such as "tla2024.+5.0V (V)" ->
    4.61, so it renders as plain table cells instead of nested JSON. Values
    that don't match this shape are passed through (dicts/lists are
    JSON-encoded so the table stays flat; scalars are kept as-is).
    """
    flat = {}
    for key, val in d.items():
        if isinstance(val, list) and val and all(_is_reading_item(x) for x in val):
            for item in val:
                label = f"{key}.{item['label']}"
                unit = item.get("unit")
                if unit:
                    label = f"{label} ({unit})"
                flat[label] = item["value"]
        elif isinstance(val, (dict, list)):
            flat[key] = json.dumps(val, ensure_ascii=False)
        else:
            flat[key] = val
    return flat


def _flatten_monitor_dict(d: dict) -> dict:
    """Flattens one channel's monitor-register dict, as returned per-channel
    by febmgr.getStatus() (readPMTMonRegisters/readLEDMonRegisters under the
    hood): {"value": v, "string": s} fields (status, alarm, ...) become
    "s (v)"; other nested dicts/lists are JSON-encoded; scalars pass through.
    """
    flat = {}
    for key, val in d.items():
        if _is_value_string_item(val):
            flat[key] = f"{val['string']} ({val['value']})"
        elif isinstance(val, (dict, list)):
            flat[key] = json.dumps(val, ensure_ascii=False)
        else:
            flat[key] = val
    return flat


def _add_sampling_arguments(sub: argparse.ArgumentParser):
    """Adds --table/--count/--interval to a method subparser, so any RPC
    call can optionally be shown as a table and/or repeated over time to
    check whether values are stable.
    """
    sub.add_argument(
        "--table", action="store_true",
        help="show dict / list-of-dict results as a table instead of JSON",
    )
    sub.add_argument(
        "--count", type=int, default=1, metavar="N",
        help="repeat the call N times (default: 1)",
    )
    sub.add_argument(
        "--interval", type=float, default=1.0, metavar="SECONDS",
        help="seconds to wait between repeated calls (default: 1.0)",
    )


def _build_namespace_parser(ns_name: str, spec: list) -> "cmd2.Cmd2ArgumentParser":
    parser = cmd2.Cmd2ArgumentParser(
        description=f"RPC commands for namespace '{ns_name}'"
    )
    subparsers = parser.add_subparsers(
        title="method", dest="method_name", required=True
    )
    for python_name, params, rtype in spec:
        sub = subparsers.add_parser(
            python_name, help=_method_help(python_name, params, rtype)
        )
        for name, ptype, required in params:
            _add_param_argument(sub, name, ptype, required)
        _add_sampling_arguments(sub)
        sub.set_defaults(func=python_name)
    return parser


FPGA_PARSER = _build_namespace_parser("fpga", mssclient.NAMESPACE_SPEC["fpga"])
SENSORS_PARSER = _build_namespace_parser("sensors", mssclient.NAMESPACE_SPEC["sensors"])
FEBMGR_PARSER = _build_namespace_parser("febmgr", mssclient.NAMESPACE_SPEC["febmgr"])

RAW_PARSER = cmd2.Cmd2ArgumentParser(
    description="Raw RPC call, useful for methods not yet present in NAMESPACE_SPEC."
)
RAW_PARSER.add_argument("method", help="e.g. febmgr.getPMTStatus")
RAW_PARSER.add_argument(
    "params",
    nargs="?",
    default="{}",
    help='parameters as JSON, e.g. {"channel": 6} or [6]',
)
_add_sampling_arguments(RAW_PARSER)

CONNECT_PARSER = cmd2.Cmd2ArgumentParser()
CONNECT_PARSER.add_argument("url", help="e.g. http://zynq:8000/rpc")

ENABLE_ALL_PARSER = cmd2.Cmd2ArgumentParser(
    description="Enable (power on) every channel defined on the FEB."
)
ENABLE_ALL_PARSER.add_argument(
    "-y", "--yes", action="store_true", help="skip the confirmation prompt"
)

DISABLE_ALL_PARSER = cmd2.Cmd2ArgumentParser(
    description="Disable (power off) every channel defined on the FEB."
)
DISABLE_ALL_PARSER.add_argument(
    "-y", "--yes", action="store_true", help="skip the confirmation prompt"
)

STATUS_PARSER = cmd2.Cmd2ArgumentParser(
    description="Show a table with the monitor registers of every online channel."
)
STATUS_PARSER.add_argument(
    "--channel_type",
    choices=[e.value for e in mssclient.DeviceType],
    default=None,
    help="filter by channel type (PMT or LED); default: both",
)

PMT_INFO_PARSER = cmd2.Cmd2ArgumentParser(
    description="Show a table with getPMTInfo() (serial numbers, fw version) "
                 "for every online PMT channel."
)

# febmgr methods that read or change which channels are online: after they
# run it's worth re-displaying the refreshed online status.
ONLINE_REFRESH_TRIGGERS = {
    "getOnlineChannels",
    "getOfflineChannels",
    "getStatus",
    "enableChannel",
    "disableChannel",
    "enableChannels",
    "disableChannels",
    "enableChannelsByMask",
    "disableChannelsByMask",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class MSSShell(cmd2.Cmd):
    """Interactive shell for the mpmt-mss RPC service."""

    def __init__(self, url: str, timeout: float = 10.0):
        super().__init__(
            persistent_history_file="~/.mss_cli_history",
            allow_cli_args=False,
        )
        self.url = url
        self.timeout = timeout
        self.client = mssclient.MSSClient(url, timeout=timeout)
        self._update_prompt()

        # commands/namespaces that aren't part of cmd2's base set
        self.default_category = "RPC commands"

    def preloop(self):
        self.poutput(
            "mpmt-mss CLI — type 'help' or '?' for the command list, "
            "'methods' for the RPC methods, 'online' for active channels.\n"
        )
        self._show_online()

    def _update_prompt(self):
        self.prompt = f"mss ({self.url})> "

    def _show_online(self):
        """Queries the server and shows the PMT/LED channels currently
        online. This is always a live query: there is no CLI-side cache.
        """
        try:
            pmt = self.client.febmgr.getOnlineChannels(channel_type=mssclient.DeviceType.PMT)
            led = self.client.febmgr.getOnlineChannels(channel_type=mssclient.DeviceType.LED)
        except mssclient.JsonRpcError as exc:
            self.perror(f"RPC error [{exc.code}] {exc.message} {exc.data or ''}".strip())
            return
        except mssclient.JsonRpcTransportError as exc:
            self.perror(f"Could not read online channels: {exc}")
            return

        pmt_str = ", ".join(str(c) for c in sorted(pmt)) or "-"
        led_str = ", ".join(str(c) for c in sorted(led)) or "-"
        self.poutput("Online channels:")
        self.poutput(f"  PMT ({len(pmt)}): {pmt_str}")
        self.poutput(f"  LED ({len(led)}): {led_str}")

    # -- shared dispatch for namespace commands ------------------------

    def _dispatch(self, ns_name: str, args: argparse.Namespace):
        method_name = args.func
        spec = dict(
            (name, (params, rtype))
            for name, params, rtype in mssclient.NAMESPACE_SPEC[ns_name]
        )
        params, _rtype = spec[method_name]

        kwargs = {}
        for name, _ptype, required in params:
            value = getattr(args, name, None)
            if value is None and not required:
                continue
            kwargs[name] = value

        ns_obj = getattr(self.client, ns_name)
        method = getattr(ns_obj, method_name)

        self._run_sampled(
            lambda: method(**kwargs),
            count=args.count,
            interval=args.interval,
            as_table=args.table,
        )

        if ns_name == "febmgr" and method_name in ONLINE_REFRESH_TRIGGERS and args.count <= 1:
            self._show_online()

    def _run_sampled(self, call_fn, count: int, interval: float, as_table: bool):
        """Calls call_fn() once, or `count` times spaced `interval` seconds
        apart, printing the result(s). call_fn takes no arguments and
        either returns the RPC result or raises mssclient.JsonRpcError /
        JsonRpcTransportError.
        """
        if count <= 1:
            try:
                result = call_fn()
            except mssclient.JsonRpcError as exc:
                self.perror(f"RPC error [{exc.code}] {exc.message} {exc.data or ''}".strip())
                return
            except mssclient.JsonRpcTransportError as exc:
                self.perror(f"Transport error: {exc}")
                return
            except TypeError as exc:
                self.perror(f"Invalid parameters: {exc}")
                return
            self._print_result(result, as_table=as_table)
            return

        samples = []
        t0 = time.monotonic()
        for i in range(count):
            try:
                result = call_fn()
            except mssclient.JsonRpcError as exc:
                self.perror(f"RPC error [{exc.code}] {exc.message} {exc.data or ''}".strip())
                return
            except mssclient.JsonRpcTransportError as exc:
                self.perror(f"Transport error: {exc}")
                return
            except TypeError as exc:
                self.perror(f"Invalid parameters: {exc}")
                return

            elapsed = time.monotonic() - t0
            samples.append((i + 1, elapsed, result))

            if isinstance(result, list) and result and all(isinstance(x, dict) for x in result):
                # a per-sample table is printed right away: merging N of
                # these into one table would be misleading (rows aren't
                # aligned by channel across samples in a stable way)
                self.poutput(f"--- sample {i + 1}/{count} (t={elapsed:.1f}s) ---")
                headers, rows = _dicts_to_table(result)
                self.poutput(_format_table(headers, rows))

            if i < count - 1:
                time.sleep(interval)

        self._print_samples_summary(samples)

    def _print_samples_summary(self, samples: list):
        first_result = samples[0][2]

        if isinstance(first_result, list) and first_result and all(isinstance(x, dict) for x in first_result):
            # already printed one table per sample above
            return

        if isinstance(first_result, dict):
            flat_samples = [
                (i, t, _flatten_result_dict(r) if isinstance(r, dict) else {})
                for i, t, r in samples
            ]
            all_keys: list = []
            for _, _, fr in flat_samples:
                for k in fr.keys():
                    if k not in all_keys:
                        all_keys.append(k)
            headers = ["#", "t(s)"] + all_keys
            rows = []
            for i, t, fr in flat_samples:
                row = [i, f"{t:.1f}"] + [fr.get(k, "") for k in all_keys]
                rows.append(row)
            self.poutput(_format_table(headers, rows))
            return

        # scalar results (int/float/str/bool/None): one row per sample
        headers = ["#", "t(s)", "value"]
        rows = [[i, f"{t:.1f}", r] for i, t, r in samples]
        self.poutput(_format_table(headers, rows))

    def _print_result(self, result, as_table: bool = False):
        if result is None:
            self.poutput("OK")
            return

        if as_table:
            if isinstance(result, dict):
                flat = _flatten_result_dict(result)
                self.poutput(_format_table(["field", "value"], list(flat.items())))
                return
            if isinstance(result, list) and result and all(isinstance(x, dict) for x in result):
                headers, rows = _dicts_to_table(result)
                self.poutput(_format_table(headers, rows))
                return
            # not tabulable (scalar, empty list, ...): fall through

        if isinstance(result, (dict, list)):
            self.poutput(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            self.poutput(result)

    # -- one generated command per namespace -----------------------------

    @cmd2.with_category("RPC commands")
    @cmd2.with_argparser(FPGA_PARSER)
    def do_fpga(self, args: argparse.Namespace):
        """Methods of the fpga namespace (FPGA registers)."""
        self._dispatch("fpga", args)

    @cmd2.with_category("RPC commands")
    @cmd2.with_argparser(SENSORS_PARSER)
    def do_sensors(self, args: argparse.Namespace):
        """Methods of the sensors namespace (housekeeping)."""
        self._dispatch("sensors", args)

    @cmd2.with_category("RPC commands")
    @cmd2.with_argparser(FEBMGR_PARSER)
    def do_febmgr(self, args: argparse.Namespace):
        """Methods of the febmgr namespace (PMT/LED channels)."""
        self._dispatch("febmgr", args)

    # -- convenience: act on every defined channel at once ---------------

    def _defined_channels(self) -> list:
        """Fetches the list of channels currently configured on the FEB
        (both PMT and LED), used by enable_all/disable_all so they don't
        depend on a hardcoded channel count.
        """
        try:
            return self.client.febmgr.getDefinedChannels()
        except mssclient.JsonRpcError as exc:
            self.perror(f"RPC error [{exc.code}] {exc.message} {exc.data or ''}".strip())
            return []
        except mssclient.JsonRpcTransportError as exc:
            self.perror(f"Could not read defined channels: {exc}")
            return []

    def _confirm(self, prompt: str) -> bool:
        answer = self.read_input(f"{prompt} [y/N] ")
        return answer.strip().lower() in ("y", "yes")

    @cmd2.with_category("RPC commands")
    @cmd2.with_argparser(ENABLE_ALL_PARSER)
    def do_enable_all(self, args: argparse.Namespace):
        """Enable (power on) every channel defined on the FEB."""
        channels = self._defined_channels()
        if not channels:
            self.perror("No defined channels to enable.")
            return
        channels = sorted(channels)
        if not args.yes and not self._confirm(
            f"Enable {len(channels)} channel(s) ({', '.join(str(c) for c in channels)})?"
        ):
            self.poutput("Aborted.")
            return
        try:
            self.client.febmgr.enableChannels(channels)
        except mssclient.JsonRpcError as exc:
            self.perror(f"RPC error [{exc.code}] {exc.message} {exc.data or ''}".strip())
            return
        except mssclient.JsonRpcTransportError as exc:
            self.perror(f"Transport error: {exc}")
            return
        self.poutput(f"Enabled {len(channels)} channel(s).")
        self._show_online()

    @cmd2.with_category("RPC commands")
    @cmd2.with_argparser(DISABLE_ALL_PARSER)
    def do_disable_all(self, args: argparse.Namespace):
        """Disable (power off) every channel defined on the FEB."""
        channels = self._defined_channels()
        if not channels:
            self.perror("No defined channels to disable.")
            return
        channels = sorted(channels)
        if not args.yes and not self._confirm(
            f"Disable {len(channels)} channel(s) ({', '.join(str(c) for c in channels)})?"
        ):
            self.poutput("Aborted.")
            return
        try:
            self.client.febmgr.disableChannels(channels)
        except mssclient.JsonRpcError as exc:
            self.perror(f"RPC error [{exc.code}] {exc.message} {exc.data or ''}".strip())
            return
        except mssclient.JsonRpcTransportError as exc:
            self.perror(f"Transport error: {exc}")
            return
        self.poutput(f"Disabled {len(channels)} channel(s).")
        self._show_online()

    @cmd2.with_category("RPC commands")
    @cmd2.with_argparser(STATUS_PARSER)
    def do_status(self, args: argparse.Namespace):
        """Show a table with the monitor registers of every online channel."""
        kwargs = {}
        if args.channel_type is not None:
            kwargs["channel_type"] = mssclient.DeviceType(args.channel_type)

        try:
            report = self.client.febmgr.getStatus(**kwargs)
        except mssclient.JsonRpcError as exc:
            self.perror(f"RPC error [{exc.code}] {exc.message} {exc.data or ''}".strip())
            return
        except mssclient.JsonRpcTransportError as exc:
            self.perror(f"Transport error: {exc}")
            return

        if not report:
            self.poutput("No online channels.")
            return

        rows = []
        for channel in sorted(report, key=int):
            row = {"channel": channel}
            row.update(_flatten_monitor_dict(report[channel]))
            rows.append(row)

        headers, table_rows = _dicts_to_table(rows)
        self.poutput(_format_table(headers, table_rows))

    @cmd2.with_category("RPC commands")
    @cmd2.with_argparser(PMT_INFO_PARSER)
    def do_pmt_info(self, _args: argparse.Namespace):
        """Show a table with getPMTInfo() (serials, fw version) for every online PMT channel."""
        try:
            channels = self.client.febmgr.getOnlineChannels(channel_type=mssclient.DeviceType.PMT)
        except mssclient.JsonRpcError as exc:
            self.perror(f"RPC error [{exc.code}] {exc.message} {exc.data or ''}".strip())
            return
        except mssclient.JsonRpcTransportError as exc:
            self.perror(f"Could not read online channels: {exc}")
            return

        if not channels:
            self.poutput("No online PMT channels.")
            return

        rows = []
        for channel in sorted(channels):
            row = {"channel": channel}
            try:
                row.update(self.client.febmgr.getPMTInfo(channel))
            except mssclient.JsonRpcError as exc:
                row["error"] = f"[{exc.code}] {exc.message}"
            except mssclient.JsonRpcTransportError as exc:
                row["error"] = str(exc)
            rows.append(row)

        headers, table_rows = _dicts_to_table(rows)
        self.poutput(_format_table(headers, table_rows))

    # -- utility ----------------------------------------------------------

    @cmd2.with_category("Utility")
    @cmd2.with_argparser(RAW_PARSER)
    def do_raw(self, args: argparse.Namespace):
        """Raw RPC call: raw <namespace.method> [params_json]."""
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError as exc:
            self.perror(f"Invalid JSON for parameters: {exc}")
            return
        self._run_sampled(
            lambda: self.client._call(args.method, params),
            count=args.count,
            interval=args.interval,
            as_table=args.table,
        )

    @cmd2.with_category("Utility")
    def do_methods(self, _):
        """List all available RPC methods (local, from NAMESPACE_SPEC)."""
        for ns_name, spec in mssclient.NAMESPACE_SPEC.items():
            self.poutput(f"[{ns_name}]")
            for python_name, params, rtype in spec:
                self.poutput(f"  {python_name}  {_method_help(python_name, params, rtype)}")

    @cmd2.with_category("Utility")
    def do_schema(self, _):
        """Query the server (GET /rpc/schema) and print the actual schema."""
        try:
            resp = self.client.session.get(f"{self.url}/schema", timeout=self.timeout)
            resp.raise_for_status()
        except Exception as exc:
            self.perror(f"Could not reach the server: {exc}")
            return
        self.poutput(json.dumps(resp.json(), indent=2, ensure_ascii=False))

    @cmd2.with_category("Utility")
    def do_server_methods(self, _):
        """Query the server (GET /rpc/methods) for the actual method list."""
        try:
            resp = self.client.session.get(f"{self.url}/methods", timeout=self.timeout)
            resp.raise_for_status()
        except Exception as exc:
            self.perror(f"Could not reach the server: {exc}")
            return
        for m in resp.json().get("methods", []):
            self.poutput(m)

    @cmd2.with_category("Utility")
    @cmd2.with_argparser(CONNECT_PARSER)
    def do_connect(self, args: argparse.Namespace):
        """Switch server: connect <url>, e.g. connect http://zynq:8000/rpc."""
        self.client.close()
        self.url = args.url
        self.client = mssclient.MSSClient(self.url, timeout=self.timeout)
        self._update_prompt()
        self.poutput(f"Connected to {self.url}")

    @cmd2.with_category("Utility")
    def do_url(self, _):
        """Show the URL of the server currently in use."""
        self.poutput(self.url)

    @cmd2.with_category("Utility")
    def do_online(self, _):
        """Query the server and show the PMT/LED channels currently online."""
        self._show_online()

    def do_quit(self, args):
        """Exit the CLI."""
        self.client.close()
        return super().do_quit(args)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://zynq:8000/rpc", help="RPC endpoint URL (default: %(default)s)")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds (default: %(default)s)")
    ns = parser.parse_args()

    shell = MSSShell(url=ns.url, timeout=ns.timeout)
    sys.exit(shell.cmdloop())


if __name__ == "__main__":
    main()
