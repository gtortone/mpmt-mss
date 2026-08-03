# mpmt-mss

mPMT Slow Control Service — a JSON-RPC service that runs on the mPMT's Zynq
SoC and exposes PMT/LED HV control, FPGA registers, and sensor readout over
HTTP. 

## Install & run

Requires Python >= 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
pip install uv
git clone <this repo>
cd mpmt-mss
uv sync
uv run mpmt-mss
```

## Running as a service

A systemd unit is included at `contrib/systemd/mpmt-mss.service`:

```bash
sudo cp contrib/systemd/mpmt-mss.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mpmt-mss
```

It assumes the repo is checked out at `/opt/mpmt-mss` (`WorkingDirectory`)
and that `uv` is at `/usr/local/bin/uv` (`ExecStart`) — adjust both if your
setup differs. Restarts automatically on failure.

## Using it

### From the CLI

An interactive shell (`mss_cli.py`) is included, with one command per RPC
method plus a few convenience commands (`status`, `enable_all`,
`calibrate_pmt`, ...). Type `help` once inside for the full list.

```bash
uv run src/mpmt_mss/cli/mss_cli.py --url http://<mss-host>:8000/rpc
```

Or, once installed under `/opt/mpmt-mss`, from anywhere:

```bash
uv --directory /opt/mpmt-mss run /opt/mpmt-mss/src/mpmt_mss/cli/mss_cli.py --url http://<mss-host>:8000/rpc
```

### From your own code

A plain Python client ships in the package - no extra install needed if
`mpmt-mss` is already a dependency of your project:

```python
from mpmt_mss.client.python.mssclient import MSSClient
from mpmt_mss.feb.devices import DeviceType

client = MSSClient("http://<mss-host>:8000/rpc")

client.febmgr.enableChannel([6])
print(client.febmgr.getPMTVoltage(6))
print(client.febmgr.getStatus(DeviceType.PMT))
```

The client mirrors the server 1:1: `client.<namespace>.<method>(...)` for
`febmgr` (PMT/LED channels), `fpga` (registers, clock, pulser, ...) and
`sensors` (housekeeping). Errors from the server raise `JsonRpcError`
(with `.code`/`.message`); connection/timeout issues raise
`JsonRpcTransportError`. More usage examples for each namespace are in
`src/mpmt_mss/client/python/*_example.py`.

A C++ client with the same shape (`mpmt_mss::MSSClient`) is also available
under `src/mpmt_mss/client/cpp/` for C++ consumers (see
`docs/slow-control-variables.md` in `mpmt-daq-interface` for one real usage
example).
