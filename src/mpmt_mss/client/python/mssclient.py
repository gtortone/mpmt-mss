from __future__ import annotations

import itertools
from enum import Enum
from typing import Any, List, Optional, Type, Union

import requests

from mpmt_mss.feb.devices import DeviceType
from mpmt_mss.feb.ledchannel import TriggerSource

# ---------------------------------------------------------------------------
# Errors and exceptions
# ---------------------------------------------------------------------------

class JsonRpcError(Exception):
    """Error returned by the server according to the JSON-RPC 2.0 standard."""

    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(f"[{code}] {message} {data}")
        self.code = code
        self.message = message
        self.data = data


class JsonRpcTransportError(Exception):
    """Transport/HTTP error (connection, timeout, non-2xx status code)."""


# ---------------------------------------------------------------------------
# Base client: handles only HTTP transport and the JSON-RPC protocol
# ---------------------------------------------------------------------------

class BaseRpcClient:
    def __init__(self, url: str, timeout: float = 10.0, session: Optional[requests.Session] = None):
        self.url = url
        self.timeout = timeout
        self._ids = itertools.count(1)
        self.session = session or requests.Session()

    def _call(self, method: str, params: Union[list, dict]) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": next(self._ids),
        }
        try:
            resp = self.session.post(self.url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise JsonRpcTransportError(str(exc)) from exc

        data = resp.json()

        if "error" in data and data["error"] is not None:
            err = data["error"]
            raise JsonRpcError(
                code=err.get("code"),
                message=err.get("message", "Unknown error"),
                data=err.get("data"),
            )

        return data.get("result")

    def notify(self, method: str, params: Union[list, dict]) -> None:
        """Send a JSON-RPC notification (no id, no response expected)."""
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            self.session.post(self.url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise JsonRpcTransportError(str(exc)) from exc

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "BaseRpcClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


class RpcNamespace:
    """Lightweight wrapper representing one JSON-RPC method prefix
    (e.g. 'febmgr', 'fpga', 'sensors'). Delegates transport to the
    parent client so there is a single HTTP session / id counter shared
    across all namespaces.
    """
 
    def __init__(self, client: "BaseRpcClient"):
        self._client = client
 
    def _call(self, method: str, params: Union[list, dict]) -> Any:
        return self._client._call(method, params)
 
    def notify(self, method: str, params: Union[list, dict]) -> None:
        self._client.notify(method, params)


ParamSpec = tuple  # (name: str, type: type, required: bool)

# ---------------------------------------------------------------------------
# Declarative spec of server-side methods
#
# Each entry: (method_name, param_type, required, return_type)
#
#   param_type None             -> the method takes no parameters
#   param_type DeviceType       -> single enum value
#   param_type int              -> single integer
#   param_type List[int]        -> list of integers
# ---------------------------------------------------------------------------
FEBMGR_METHODS: list[tuple[str, list[ParamSpec], type]] = [
    ("getDefinedChannels",      [("channel_type", Optional[DeviceType], False)],        List[int]),
    ("getOnlineChannels",       [("channel_type", Optional[DeviceType], False)],        List[int]),
    ("getOfflineChannels",      [("channel_type", Optional[DeviceType], False)],        List[int]),
    ("getStatus",               [("channel_type", Optional[DeviceType], False)],        List[dict]),
    ("enableChannel",           [("channel", int, True)],                               type(None)),
    ("disableChannel",          [("channel", int, True)],                               type(None)),
    ("enableChannels",          [("channels", List[int], True)],                        type(None)),
    ("disableChannels",         [("channels", List[int], True)],                        type(None)),
    ("enableChannelsByMask",    [("mask", int, True)],                                  type(None)),
    ("disableChannelsByMask",   [("mask", int, True)],                                  type(None)),

    ("getPMTStatus",            [("channel", int, True)],                               dict), 
    ("getPMTVoltage",           [("channel", int, True)],                               float),
    ("getPMTVoltageSet",        [("channel", int, True)],                               float),
    ("setPMTVoltageSet",        [("channel", int, True), ("value", int, True)],         type(None)),
    ("getPMTCurrent",           [("channel", int, True)],                               float),
    ("getPMTTemperature",       [("channel", int, True)],                               float),
    ("getPMTRateRampup",        [("channel", int, True)],                               int),
    ("getPMTRateRampdown",      [("channel", int, True)],                               int),
    ("setPMTRateRampup",        [("channel", int, True), ("value", int, True)],         type(None)),
    ("setPMTRateRampdown",      [("channel", int, True), ("value", int, True)],         type(None)),
    ("setPMTLimitVoltage",      [("channel", int, True), ("value", int, True)],         type(None)),
    ("setPMTLimitCurrent",      [("channel", int, True), ("value", int, True)],         type(None)),
    ("setPMTLimitTemperature",  [("channel", int, True), ("value", int, True)],         type(None)),
    ("setPMTLimitTriptime",     [("channel", int, True), ("value", int, True)],         type(None)),
    ("setPMTThreshold",         [("channel", int, True), ("value", float, True)],       type(None)),
    ("getPMTThreshold",         [("channel", int, True)],                               float),
    ("getPMTAlarm",             [("channel", int, True)],                               dict),
    ("getPMTVref",              [("channel", int, True)],                               float),
    ("powerPMTOn",              [("channel", int, True)],                               type(None)),
    ("powerPMTOff",             [("channel", int, True)],                               type(None)),
    ("resetPMT",                [("channel", int, True)],                               type(None)),
    ("getPMTInfo",              [("channel", int, True)],                               dict), 
    ("setPMTSerialNumber",      [("channel", int, True), ("sn", str, True)],            type(None)), 
    ("setPMTHVSerialNumber",    [("channel", int, True), ("sn", str, True)],            type(None)), 
    ("setPMTFEBSerialNumber",   [("channel", int, True), ("sn", str, True)],            type(None)), 
    ("readPMTMonRegisters",     [("channel", int, True)],                               dict), 
    ("readPMTCalibRegisters",   [("channel", int, True)],                               dict), 
    ("writePMTCalibSlope",      [("channel", int, True), ("value", float, True)],       type(None)), 
    ("writePMTCalibOffset",     [("channel", int, True), ("value", float, True)],       type(None)), 
    ("writePMTCalibDiscr",      [("channel", int, True), ("value", float, True)],       type(None)), 

    ("getLEDStatus",            [("channel", int, True)],                               dict), 
    ("getLEDInfo",              [("channel", int, True)],                               dict), 
    ("getLEDTriggerStatus",     [("channel", int, True)],                               dict), 
    ("getLEDBiasStatus",        [("channel", int, True)],                               dict), 
    ("getLEDBiasVoltage",       [("channel", int, True)],                               float),
    ("readLEDBiasVoltage",      [("channel", int, True)],                               float),
    ("getLEDTriggerSource",     [("channel", int, True)],                               dict), 
    ("getLEDCurrent",           [("channel", int, True)],                               float),
    ("getLEDChannels",          [("channel", int, True)],                               List[int]),
    ("readLEDMonRegisters",     [("channel", int, True)],                               dict),
    ("powerLEDOn",              [("channel", int, True)],                               type(None)),
    ("powerLEDOff",             [("channel", int, True)],                               type(None)),
    ("setLEDTrigger",           [("channel", int, True), ("value", bool, True)],         type(None)),
    ("setLEDTriggerSource",     [("channel", int, True), ("source", TriggerSource, True)],  type(None)),
    ("setLEDBias",              [("channel", int, True), ("value", bool, True)],         type(None)),
    ("setLEDBiasVoltage",       [("channel", int, True), ("value", float, True)],       type(None)),
    ("setLEDChannels",          [("channel", int, True), ("channels", List[int], True), ("append", Optional[bool], False)], type(None)),
]

FPGA_METHODS: list[tuple[str, list[ParamSpec], type]] = [
    ("readRegister",            [("address", int, True)],                               int),
    ("writeRegister",           [("address", int, True), ("value", int, True)],         int),
]
 
SENSORS_METHODS: list[tuple[str, list[ParamSpec], type]] = [
]
 
# One entry per JSON-RPC prefix. The dict key is both the wire-level prefix
# (key + ".") and the attribute name exposed on the client
# (e.g. client.febmgr, client.fpga, client.sensors).
NAMESPACE_SPEC: dict[str, list[tuple[str, list[ParamSpec], type]]] = {
    "febmgr": FEBMGR_METHODS,
    "fpga": FPGA_METHODS,
    "sensors": SENSORS_METHODS,
}


# ---------------------------------------------------------------------------
# Dynamic generation of client methods
# ---------------------------------------------------------------------------

def _pack_value(value: Any) -> Any:
    """Convert enums/lists of enums into JSON-serializable values."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [_pack_value(v) for v in value]
    return value
 
 
def _build_params(python_name: str, params: list[ParamSpec], values: tuple) -> list:
    """Turn positional argument values into a JSON-RPC params list,
    validating required parameters and dropping trailing omitted optionals.
    """
    packed: list = []
    for (name, _ptype, required), value in zip(params, values):
        if value is None:
            if required:
                raise TypeError(f"{python_name}(): parameter '{name}' is required")
            break  # trailing optional omitted: stop here, don't send later params
        packed.append(_pack_value(value))
    return packed
 
 
def _make_method(python_name: str, wire_name: str, params: list[ParamSpec], return_type: type):
    """Create an actual client function for a remote method, with a real
    Python signature matching the parameter names in the spec.
 
    python_name: attribute name used on the client (e.g. 'setPMTVoltageSet')
    wire_name:   method name actually sent in the JSON-RPC request
                 (e.g. 'febmgr.setPMTVoltageSet')
    """
    arg_defs = ", ".join(name if required else f"{name}=None" for name, _t, required in params)
    call_values = ", ".join(name for name, _t, _r in params)
    signature = f"self{', ' + arg_defs if arg_defs else ''}"
 
    src = (
        f"def {python_name}({signature}):\n"
        f"    values = ({call_values}{',' if len(params) == 1 else ''})\n"
        f"    rpc_params = _build_params({python_name!r}, _params_spec, values)\n"
        f"    return self._call({wire_name!r}, rpc_params)\n"
    )
 
    namespace: dict[str, Any] = {"_build_params": _build_params, "_params_spec": params}
    exec(src, namespace)  # noqa: S102 - controlled input, only used to build a typed signature
    method = namespace[python_name]
 
    params_doc = "\n".join(
        f"    {name}: {getattr(t, '__name__', str(t))} ({'required' if required else 'optional'})"
        for name, t, required in params
    ) or "    (none)"
    rtype_name = getattr(return_type, "__name__", str(return_type))
    method.__doc__ = f"Calls the remote method '{wire_name}'.\n\nParameters:\n{params_doc}\n\nReturns: {rtype_name}"
    method.__qualname__ = python_name
    return method
 

def build_client_class(
    spec: list[tuple[str, list[ParamSpec], type]],
    base: Type = BaseRpcClient,
    class_name: str = "RpcClient",
    rpc_prefix: str = "",
) -> Type:
    """Dynamically build a class with one method per spec entry.
 
    Works both for the top-level client (base=BaseRpcClient) and for
    lightweight namespace wrappers (base=RpcNamespace) — both expose
    a compatible self._call(method, params).
 
    rpc_prefix: prepended to each method name only in the JSON-RPC request
                (e.g. "febmgr." turns getStatus() into a call to
                "febmgr.getStatus" on the wire), while the Python attribute
                name stays unprefixed (client.febmgr.getStatus()).
    """
    namespace: dict[str, Any] = {}
    for python_name, params, rtype in spec:
        if python_name in namespace:
            raise ValueError(f"Duplicate method in spec: {python_name}")
        wire_name = f"{rpc_prefix}{python_name}"
        namespace[python_name] = _make_method(python_name, wire_name, params, rtype)
    return type(class_name, (base,), namespace)
 
 
def build_rpc_client(
    namespace_spec: dict[str, list[tuple[str, list[ParamSpec], type]]],
    base: Type[BaseRpcClient] = BaseRpcClient,
    class_name: str = "RpcClient",
) -> Type[BaseRpcClient]:
    """Build a top-level client class exposing one sub-namespace attribute
    per JSON-RPC prefix, e.g.:
 
        client.febmgr.getStatus()      -> wire method "febmgr.getStatus"
        client.fpga.reset()            -> wire method "fpga.reset"
        client.sensors.readTemperature() -> wire method "sensors.readTemperature"
 
    This avoids name collisions between methods with the same name in
    different namespaces, and keeps the wire prefix explicit and visible
    in the calling code.
    """
    namespace_classes: dict[str, Type[RpcNamespace]] = {
        ns_name: build_client_class(
            spec,
            base=RpcNamespace,
            class_name=f"{ns_name.capitalize()}Namespace",
            rpc_prefix=f"{ns_name}.",
        )
        for ns_name, spec in namespace_spec.items()
    }
 
    def __init__(self, url: str, timeout: float = 10.0, session: Optional[requests.Session] = None):
        base.__init__(self, url, timeout=timeout, session=session)
        for ns_name, ns_class in namespace_classes.items():
            setattr(self, ns_name, ns_class(self))
 
    return type(class_name, (base,), {"__init__": __init__})
 
 
MSSClient = build_rpc_client(NAMESPACE_SPEC)
 

