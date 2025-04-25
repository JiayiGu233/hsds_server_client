
import os
import subprocess
from datetime import datetime, timedelta
import requests
import h5pyd
import numpy as np
import base64

# ===================== GLOBAL CONST =====================
DOMAIN_PREFIX = "/home/admin/"        
ADMIN_USERNAME = "admin"               
ADMIN_PASSWORD = "admin"              
TIME_SIGNAL_NAME = "@Time@"           
SAMPLE_FREQUENCY_ATTR = "sampleFrequency"
TRIGGER_TIME_ATTR = "triggerTimeSystemText"
DEFAULT_SAMPLE_FREQUENCY = 4000       
GLOBAL_ENDPOINT = None


class Attributes:
    def __init__(self, name, type, value):
        self.name = name
        self.type = type
        self.value = value

    def _clean_value(self, val):
        if isinstance(val, np.ndarray):
            return self._clean_value(val.tolist())
        elif isinstance(val, list):
            return [self._clean_value(x) for x in val]
        elif isinstance(val, (bytes, np.bytes_)):
            try:
                return val.decode('utf-8')
            except Exception:
                return str(val)
        else:
            return val

    def __repr__(self):
        cleaned = self._clean_value(self.value)
        return f"{self.name:<20}: {cleaned}"

class SignalInfo:
    def __init__(self, relative_path, attributes):
        self.relative_path = relative_path
        self.attributes = attributes

    def __repr__(self):
        return f"{self.relative_path}"

class TimeRange:
    def __init__(self, start, end):
        self.start = start
        self.end = end

    def __repr__(self):
        return f"{self.start} to {self.end}"

class FileInfo:
    def __init__(self, name, frequency, time_range: TimeRange, signals):
        self.name = name
        self.frequency = frequency
        self.time_range = time_range
        if isinstance(signals, list):
            self.signals = signals
        else:
            self.signals = [signals]

    def __repr__(self):
        signals_list = [s.relative_path for s in self.signals]
        signals_str = ", ".join(signals_list)
        return (f"FileInfo:\n"
                f"  Name: {self.name}\n"
                f"  Frequency: {self.frequency}\n"
                f"  Time Range: {self.time_range}\n"
                f"  Signals: [{signals_str}]")

class FrequencyInfo:
    def __init__(self, file_name, frequency, time_range: TimeRange):
        self.file_name = file_name
        self.frequency = frequency
        self.time_range = time_range

    def __repr__(self):
        return f"file={self.file_name}, frequency={self.frequency}, time_range={self.time_range}"

class Statistics:
    def __init__(self, mean, max_val, min_val, three_sigma):
        self.mean = mean
        self.max = max_val
        self.min = min_val
        self.three_sigma = three_sigma

    def __repr__(self):
        return (f"Statistics(mean={self.mean}, max={self.max}, "
                f"min={self.min}, three_sigma={self.three_sigma})")

# ===================== 帮助函数 =====================

def parse_trigger_time(time_str: str) -> datetime:
    return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")

def merge_time_intervals(intervals):
    if not intervals:
        return []
    intervals_sorted = sorted(intervals, key=lambda x: x[0])
    merged = [intervals_sorted[0]]
    for current_start, current_end in intervals_sorted[1:]:
        last_start, last_end = merged[-1]
        if current_start <= last_end:
            merged[-1] = (last_start, max(last_end, current_end))
        else:
            merged.append((current_start, current_end))
    return merged

# ===================== HSDS 数据访问客户端 =====================

class HSDSClient:
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.admin_username = ADMIN_USERNAME
        self.admin_password = ADMIN_PASSWORD
        global GLOBAL_ENDPOINT
        GLOBAL_ENDPOINT = self.endpoint  
        print("HSDSClient initialized.")

    def traverse_signals(self, domain):
        signals = {}
        def visitor(name, obj):
            if hasattr(obj, "shape"):
                full_path = name if name.startswith("/") else "/" + name
                signals[full_path] = obj
        with h5pyd.File(domain, 'r', endpoint=self.endpoint,
                        username=self.admin_username, password=self.admin_password) as f:
            f.visititems(visitor)
        return signals

    def list_all_files_name(self):
        try:
            result = subprocess.run([
            "hsls",
            "-e", self.endpoint,
            "-u", self.admin_username,
            "-p", self.admin_password,
            DOMAIN_PREFIX
        ],
                                    capture_output=True, text=True, check=True)
            output = result.stdout.strip()
            lines = output.splitlines()
            strc_files = []
            for line in lines:
                if not line.strip():
                    continue
                tokens = line.split()
                if len(tokens) >= 5 and tokens[1].lower() == "domain":
                    path_token = tokens[-1]
                    if path_token.startswith(DOMAIN_PREFIX):
                        fname = path_token[len(DOMAIN_PREFIX):]
                    else:
                        fname = path_token
                    if fname.lower().endswith(".strc"):
                        strc_files.append(fname)
            return strc_files
        except Exception as e:
            print("Error listing folder with hsls:", e)
            return []

    def _get_all_domains(self):
        strc_files = self.list_all_files_name()
        domains = [DOMAIN_PREFIX + fname for fname in strc_files]
        return domains

    def _has_signal(self, domain, signal_path):
        with h5pyd.File(domain, 'r', endpoint=self.endpoint,
                        username=self.admin_username, password=self.admin_password) as f:
            return signal_path.lstrip('/') in f

    def list_files_with_signal(self, signal_path):
        print(f"signal {signal_path} exists in files:")
        for domain in self._get_all_domains():
            if self._has_signal(domain, signal_path):
                file_name = domain[len(DOMAIN_PREFIX):]
                print(f"{file_name}")

    def get_signal_attributes(self, signal_path: str) -> list:
        for domain in self._get_all_domains():
            if self._has_signal(domain, signal_path):
                try:
                    with h5pyd.File(domain, 'r', endpoint=self.endpoint,
                                    username=self.admin_username, password=self.admin_password) as f:
                        if signal_path.lstrip('/') in f:
                            ds = f[signal_path.lstrip('/')]
                            attributes_list = []
                            for key, value in ds.attrs.items():
                                attr_type = type(value).__name__
                                attr_obj = Attributes(name=key, type=attr_type, value=value)
                                attributes_list.append(attr_obj)
                            return attributes_list
                except Exception as e:
                    print(f"Error reading attributes for {signal_path} in domain {domain}: {e}")
        return []

    def get_signals_in_all_files(self):
        domains = self._get_all_domains()
        signal_set = set()
        for d in domains:
            ds = self.traverse_signals(d)
            for path in ds.keys():
                signal_set.add(path)
        return sorted(list(signal_set))

    def _get_time_signal_info(self, domain):
        with h5pyd.File(domain, 'r', endpoint=self.endpoint,
                        username=self.admin_username, password=self.admin_password) as f:
            if TIME_SIGNAL_NAME not in f:
                return None
            time_dset = f[TIME_SIGNAL_NAME]
            freq = time_dset.attrs.get(SAMPLE_FREQUENCY_ATTR, DEFAULT_SAMPLE_FREQUENCY)
            trigger_str = time_dset.attrs.get(TRIGGER_TIME_ATTR, None)
            if not trigger_str:
                return None
            trigger_dt = parse_trigger_time(trigger_str)
            time_data = time_dset[...]
            t_min = float(np.min(time_data))
            t_max = float(np.max(time_data))
            return {"frequency": freq, "trigger_dt": trigger_dt, "t_min": t_min, "t_max": t_max}

    def get_file_info(self, filename: str) -> FileInfo:
        domain = DOMAIN_PREFIX + filename
        frequency = None
        time_range_obj = None
        signals_list = []
        try:
            with h5pyd.File(domain, 'r', endpoint=self.endpoint,
                            username=self.admin_username, password=self.admin_password) as f:
                if TIME_SIGNAL_NAME in f:
                    time_dset = f[TIME_SIGNAL_NAME]
                    freq = time_dset.attrs.get(SAMPLE_FREQUENCY_ATTR, DEFAULT_SAMPLE_FREQUENCY)
                    trigger_str = time_dset.attrs.get(TRIGGER_TIME_ATTR, None)
                    if trigger_str:
                        trigger_dt = parse_trigger_time(trigger_str)
                        time_data = time_dset[...]
                        t_min = float(np.min(time_data))
                        t_max = float(np.max(time_data))
                        frequency = freq
                        time_range_obj = TimeRange(trigger_dt + timedelta(seconds=t_min),
                                                  trigger_dt + timedelta(seconds=t_max))
            ds_dict = self.traverse_signals(domain)
            for ds_path, _ in ds_dict.items():
                if ds_path == "/" + TIME_SIGNAL_NAME:
                    continue
                ds_attrs = self.get_signal_attributes(ds_path)
                signals_list.append(SignalInfo(relative_path=ds_path, attributes=ds_attrs))
        except Exception as e:
            print(f"Error reading file info from {domain}: {e}")
        return FileInfo(name=filename, frequency=frequency, time_range=time_range_obj, signals=signals_list)

    def list_all_files_info(self) -> list:
        file_infos = []
        strc_files = self.list_all_files_name()
        for fname in strc_files:
            fi = self.get_file_info(fname)
            file_infos.append(fi)
        return file_infos

    def get_signal_time_ranges(self, signal_path: str):
        intervals = []
        for domain in self._get_all_domains():
            if not self._has_signal(domain, signal_path):
                continue
            info = self._get_time_signal_info(domain)
            if not info:
                continue
            start_dt = info["trigger_dt"] + timedelta(seconds=info["t_min"])
            end_dt = info["trigger_dt"] + timedelta(seconds=info["t_max"])
            intervals.append((start_dt, end_dt))
        merged = merge_time_intervals(intervals)
        return [TimeRange(s, e) for s, e in merged]

    def get_signal_frequency_info(self, signal_path: str):
        result = []
        for domain in self._get_all_domains():
            if not self._has_signal(domain, signal_path):
                continue
            info = self._get_time_signal_info(domain)
            if not info:
                continue
            freq = info["frequency"]
            start_dt = info["trigger_dt"] + timedelta(seconds=info["t_min"])
            end_dt = info["trigger_dt"] + timedelta(seconds=info["t_max"])
            tr = TimeRange(start_dt, end_dt)
            file_name = domain[len(DOMAIN_PREFIX):]
            result.append(FrequencyInfo(file_name=file_name, frequency=freq, time_range=tr))
        return result

    def get_file_signal_data_in_absolute_time_range(self, filename: str, signal_name: str, start: datetime, end: datetime):
        domain = DOMAIN_PREFIX + filename
        info = self._get_time_signal_info(domain)
        if not info:
            print(f"Error: No time signal info for {filename}")
            return None
        trigger_dt = info["trigger_dt"]
        relative_start = (start - trigger_dt).total_seconds()
        relative_end = (end - trigger_dt).total_seconds()
        return self.get_file_signal_data_in_relative_time_range(filename, signal_name, relative_start, relative_end)

    def get_file_signal_data_in_relative_time_range(self, filename, signal_name, t_start, t_end):
        domain = DOMAIN_PREFIX + filename
        with h5pyd.File(domain, 'r', endpoint=self.endpoint,
                        username=ADMIN_USERNAME, password=ADMIN_PASSWORD) as f:
            if TIME_SIGNAL_NAME not in f or signal_name not in f:
                return None
            time_data = f[TIME_SIGNAL_NAME][...]
            data = f[signal_name][...]
            indices = np.where((time_data >= t_start) & (time_data <= t_end))[0]
            return data[indices]

    def get_signal_data_in_absolute_time_range(self, signal_name, start: datetime, end: datetime):
        combined = []
        for d in self._get_all_domains():
            f = d[len(DOMAIN_PREFIX):]
            d_data = self.get_file_signal_data_in_absolute_time_range(f, signal_name, start, end)
            if d_data is not None and d_data.size > 0:
                combined.append(d_data)
        if combined:
            return np.concatenate(combined)
        return np.array([])

    def analyze_data(self, data):
        if data.size == 0:
            return Statistics(0, 0, 0, 0)
        mean = np.mean(data)
        maximum = np.max(data)
        minimum = np.min(data)
        three_sigma = 3 * np.std(data)
        return Statistics(mean, maximum, minimum, three_sigma)


# if __name__ == "__main__":
#     endpoint = "http://10.86.18.139:5101"  # 替换mpc地址
#     client = HSDSClient(endpoint=endpoint)

#     files = client.list_all_files_name()
#     print("All files found:")
#     for f in files:
#         print("  ", f)

#     signal_name = "AxisTrans1/Monitor/PosAct"  # 根据实际情况替换
#     time_ranges = client.get_signal_time_ranges(signal_name)
#     print(f"\nTime ranges for signal '{signal_name}':")
#     for tr in time_ranges:
#         print("  ", tr)

#     client.list_files_with_signal(signal_name)
    
#     t_start = datetime(2025, 3, 7, 11, 48, 42, 583000)
#     t_end = datetime(2025, 3, 7, 11, 49, 52, 999999)
#     data = client.get_signal_data_in_absolute_time_range("AxisTrans1/Monitor/PosAct", t_start, t_end)    
#     stats = client.analyze_data(data)
#     print("Data statistics:", stats)

#     r_start, r_end = 5.89189, 6.99999
#     combined_data = client.get_file_signal_data_in_relative_time_range("20250304_160317_testmove.strc", signal_name, r_start, r_end)
#     if combined_data is not None:
#         print(f"\nCombined data shape for '{signal_name}' between {t_start} and {t_end}: {combined_data.shape}")
#         stats = client.analyze_data(combined_data)
#         print("Data statistics:", stats)
