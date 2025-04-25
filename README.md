# HSDS Trace Server & Python SDK

> One-stop solution to serve `.strc` trace files over **HDF5 REST (HSDS)** and analyze them from any host PC.

---

##  Server-Side Setup (MPC Machine)

###  Installation Steps

1. Visit the [Releases Page](https://git3.sioux.asia:8443/jiayi.gu/hsds_server_client/-/releases)
2. Download **`hsds_installer.zip`**
3. Log into the **MPC**
4. Extract the ZIP to any folder 
5. Open PowerShell **as Administrator** and run:

```powershell
cd <path to the extracted folder>
./install.ps1
```

You will be prompted to enter one or more **trace directories** that contain `.strc` files.

###  Deployment Summary

| Item                     | Path                                      | Description                            |
|--------------------------|-------------------------------------------|----------------------------------------|
| Logs                     | `C:\Sioux\hsds_installer\logs`         | `hs.log`, `watchdog_runtime.log`       |
| Trace Dir Configuration  | `C:\Sioux\hsds_installer\trace_path.json` | JSON config of trace folders         |

Two services will auto-start on boot:
- `HSDS_Server` — exposes trace files via REST API (`http://<ip of MPC>:5101`)
- `Watchdog_Service` — monitors and auto-uploads `.strc` files

---

##  Client-Side Usage(Host PC)

###  Download the SDK

From the same [Release Page](https://git3.sioux.asia:8443/jiayi.gu/hsds_server_client/-/releases), download one of:
- `hsds_client-x.x.x-py3-none-any.whl`(recommended)
- `hsds_client-x.x.x.tar.gz`

###  Installation 

```bash
pip install C:\path\to\hsds_client-x.x.x.whl
```

---

##  CLI Tool – `hscli`

###  Configuration

Set the MPC IP address first:

```bash
hscli config set-mpc-address 10.86.18.139
```

You can retrieve it anytime with:

```bash
hscli config get-mpc-address
```

###  Commands

| Command                | Description                                         |
|------------------------|-----------------------------------------------------|
| `hscli list`           | List all `.strc` files on server                    |
| `hscli list-signals`   | List all signals across trace files                 |
| `hscli get-data`       | Fetch signal values for a given time range         |
| `hscli analyze`        | Compute statistics (mean, min, max, 3σ)            |
| `hscli test`  | Check MPC connection and server status             |

---

##  SDK Usage in Python

###  Example

```python
from datetime import datetime
from hsds_client.core import HSDSClient

client = HSDSClient("http://10.86.18.139:5101")
print(client.list_all_files_name())

# Get signal ranges
ranges = client.get_signal_time_ranges("AxisTrans1/Monitor/PosAct")
for r in ranges:
    print(r)

# Get and analyze signal data
start = datetime(2025, 3, 7, 11, 48, 42, 583000)
end   = datetime(2025, 3, 7, 11, 49, 52, 999999)
data = client.get_signal_data_in_absolute_time_range("AxisTrans1/Monitor/PosAct", start, end)
print(client.analyze_data(data))
```

###  Public Classes

| Class           | Role                                  |
|------------------|---------------------------------------|
| `HSDSClient`     | Main interface for interacting with HSDS |
| `FileInfo`       | Metadata of a single `.strc` file     |
| `SignalInfo`     | Signal path and attributes            |
| `TimeRange`      | Represents a [start, end] interval    |
| `FrequencyInfo`  | Frequency and time coverage           |
| `Statistics`     | mean / min / max / 3σ                 |

---

