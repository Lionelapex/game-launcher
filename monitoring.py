"""
Hardware monitoring service for Game Launcher.
Collects real CPU / RAM / GPU / storage info from the host, normalising
unavailable metrics to None so the UI can show an "unavailable" indicator.

CPU/RAM/storage use psutil. GPU model comes from WMI. GPU utilisation,
temperature and VRAM use NVIDIA's NVML when an NVIDIA GPU is present; on
AMD / Intel GPUs those metrics are reported as None (unavailable).
"""

import os

try:
    import psutil
    HAS_PSUTIL = True
except Exception:
    HAS_PSUTIL = False

try:
    import win32com.client
    HAS_WMI = True
except Exception:
    HAS_WMI = False

_nvml = None          # pynvml module if successfully initialised, else None
_nvml_checked = False


def _init_nvml():
    global _nvml, _nvml_checked
    if _nvml_checked:
        return _nvml
    _nvml_checked = True
    try:
        import pynvml
        pynvml.nvmlInit()
        pynvml.nvmlDeviceGetHandleByIndex(0)
        _nvml = pynvml
    except Exception:
        _nvml = None
    return _nvml


def _gb(n):
    return n / (1024 ** 3)


def _cpu_model():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        v, _ = winreg.QueryValueEx(k, "ProcessorNameString")
        winreg.CloseKey(k)
        return v.strip()
    except Exception:
        return "Unknown CPU"


def get_cpu():
    if not HAS_PSUTIL:
        return {"model": None, "usage": None, "clock_mhz": None,
                "cores": None, "threads": None, "temp": None}
    try:
        freq = psutil.cpu_freq()
        return {
            "model": _cpu_model(),
            "usage": psutil.cpu_percent(interval=None),
            "clock_mhz": round(freq.current) if freq and freq.current else None,
            "cores": psutil.cpu_count(logical=False),
            "threads": psutil.cpu_count(logical=True),
            "temp": None,   # requires third-party driver access
        }
    except Exception:
        return {"model": _cpu_model(), "usage": None, "clock_mhz": None,
                "cores": None, "threads": None, "temp": None}


def get_ram():
    if not HAS_PSUTIL:
        return {"total": None, "used": None, "available": None, "percent": None}
    try:
        vm = psutil.virtual_memory()
        return {"total": vm.total, "used": vm.used,
                "available": vm.available, "percent": vm.percent}
    except Exception:
        return {"total": None, "used": None, "available": None, "percent": None}


def get_gpu():
    name = None
    if HAS_WMI:
        try:
            wmi = win32com.client.GetObject("winmgmts:")
            for g in wmi.InstancesOf("Win32_VideoController"):
                name = g.Name
                break
        except Exception:
            name = None

    util = temp = vram_used = vram_total = None
    nv = _init_nvml()
    if nv is not None:
        try:
            h = nv.nvmlDeviceGetHandleByIndex(0)
            util = nv.nvmlDeviceGetUtilizationRates(h).gpu
            try:
                temp = nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU)
            except Exception:
                temp = None
            mem = nv.nvmlDeviceGetMemoryInfo(h)
            vram_used, vram_total = mem.used, mem.total
        except Exception:
            util = temp = vram_used = vram_total = None

    return {"name": name, "util": util, "temp": temp,
            "vram_used": vram_used, "vram_total": vram_total}


def get_storage():
    vols = []
    if not HAS_PSUTIL:
        return vols
    try:
        import win32api
        _has_win32api = True
    except Exception:
        _has_win32api = False

    for p in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(p.mountpoint)
        except Exception:
            continue
        if u.total < 1 * 1024 ** 3:      # skip tiny/EFI/DVD partitions
            continue
        label = ""
        if _has_win32api and hasattr(win32api, "GetVolumeInformation"):
            try:
                label = win32api.GetVolumeInformation(p.mountpoint.rstrip("\\") + "\\")[0]
            except Exception:
                label = ""
        vols.append({
            "drive": p.mountpoint,
            "label": label,
            "total": u.total,
            "used": u.used,
            "free": u.free,
            "percent": u.percent,
        })
    return vols


def collect():
    """One snapshot of all monitors in a single dict."""
    return {
        "cpu": get_cpu(),
        "ram": get_ram(),
        "gpu": get_gpu(),
        "storage": get_storage(),
    }


def prime_cpu():
    """Warm up psutil's CPU-percent baseline (call once in a background thread)."""
    if HAS_PSUTIL:
        try:
            psutil.cpu_percent(interval=1.0)
        except Exception:
            pass