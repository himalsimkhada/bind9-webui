"""Prometheus-style process metrics for the BIND9 backend, dependency-free.

Reads live process state from /proc (Linux) so no psutil is required.
Exposes the standard process gauges plus our per-service health/readiness
and HTTP request counters, rendered in the Prometheus text format.
"""
import os
import platform
import time
from collections import defaultdict

SERVICE_NAME = os.environ.get("SERVICE_NAME", "bind9-webui")

# ── HTTP request bookkeeping (fed by Flask before/after request hooks) ────
_HTTP_TOTAL = 0
_HTTP_ACTIVE = 0
_HTTP_ERROR = 0
_HTTP_BY_CODE = defaultdict(int)
_START_TIME = time.time()
_PROCESS_READY = True
_PROCESS_HEALTHY = True


def set_healthy(value):
    global _PROCESS_HEALTHY
    _PROCESS_HEALTHY = value


def record_request_started():
    global _HTTP_ACTIVE
    _HTTP_ACTIVE += 1


def record_request_finished(status_code):
    global _HTTP_TOTAL, _HTTP_ACTIVE, _HTTP_ERROR
    _HTTP_TOTAL += 1
    _HTTP_ACTIVE = max(0, _HTTP_ACTIVE - 1)
    _HTTP_BY_CODE[status_code] += 1
    if status_code >= 500:
        _HTTP_ERROR += 1


def set_ready(value):
    global _PROCESS_READY
    _PROCESS_READY = value


def ready():
    return _PROCESS_READY


# ── /proc helpers ──────────────────────────────────────────────────────────

def _clock_ticks():
    try:
        return os.sysconf("SC_CLK_TCK") or 100
    except (ValueError, OSError):
        return 100


def _page_size():
    try:
        return os.sysconf("SC_PAGE_SIZE") or 4096
    except (ValueError, OSError):
        return 4096


def _stat_self():
    """Parse /proc/self/stat. comm may contain spaces, so split after ')'."""
    data = open("/proc/self/stat").read()
    rest = data[data.rfind(")") + 2:].split()
    tck = _clock_ticks()
    return {
        "utime": int(rest[11]) / tck,      # field 14 (user CPU ticks)
        "stime": int(rest[12]) / tck,      # field 15 (sys CPU ticks)
        "start_ticks": int(rest[19]),      # field 22 (start time in ticks)
        "vsize": int(rest[20]),            # field 23 (virtual memory bytes)
        "rss_pages": int(rest[21]),        # field 24 (resident pages)
    }


def _proc_io():
    out = {}
    try:
        for line in open("/proc/self/io"):
            k, _, v = line.partition(":")
            if k:
                out[k.strip()] = int(v.strip())
    except FileNotFoundError:
        pass
    return out


def _boot_time():
    """System boot time as a unix epoch by subtracting /proc/uptime from now."""
    uptime = float(open("/proc/uptime").read().split()[0])
    return time.time() - uptime


def process_metrics():
    st = _stat_self()
    io = _proc_io()
    start = _boot_time() + st["start_ticks"] / _clock_ticks()
    return {
        "process_resident_memory_bytes": st["rss_pages"] * _page_size(),
        "process_virtual_memory_bytes": st["vsize"],
        "process_cpu_seconds_total": st["utime"] + st["stime"],
        "process_start_time_seconds": start,
        "process_uptime_seconds": max(0.0, time.time() - start),
        "process_io_read_bytes": io.get("read_bytes", 0),
        "process_io_write_bytes": io.get("write_bytes", 0),
        "process_io_read_syscalls": io.get("syscr", 0),
        "process_io_write_syscalls": io.get("syscw", 0),
        "process_open_fds": len(os.listdir("/proc/self/fd")),
        "process_threads": _thread_count(),
    }


def _thread_count():
    try:
        for line in open("/proc/self/status"):
            if line.startswith("Threads:"):
                return int(line.split()[1])
    except FileNotFoundError:
        pass
    return 1


def metrics_text():
    p = process_metrics()
    boot = _boot_time()
    lines = [
        "# HELP process_resident_memory_bytes Resident memory size in bytes.",
        "# TYPE process_resident_memory_bytes gauge",
        f'process_resident_memory_bytes{{service="{SERVICE_NAME}"}} {int(p["process_resident_memory_bytes"])}',
        "# HELP process_virtual_memory_bytes Virtual memory size in bytes.",
        "# TYPE process_virtual_memory_bytes gauge",
        f'process_virtual_memory_bytes{{service="{SERVICE_NAME}"}} {int(p["process_virtual_memory_bytes"])}',
        "# HELP process_cpu_seconds_total Total user and system CPU time spent in seconds.",
        "# TYPE process_cpu_seconds_total counter",
        f'process_cpu_seconds_total{{service="{SERVICE_NAME}"}} {p["process_cpu_seconds_total"]:.6f}',
        "# HELP process_start_time_seconds Start time of the process since unix epoch in seconds.",
        "# TYPE process_start_time_seconds gauge",
        f'process_start_time_seconds{{service="{SERVICE_NAME}"}} {p["process_start_time_seconds"]:.3f}',
        "# HELP process_uptime_seconds Seconds since the process started.",
        "# TYPE process_uptime_seconds gauge",
        f'process_uptime_seconds{{service="{SERVICE_NAME}"}} {p["process_uptime_seconds"]:.3f}',
        "# HELP process_io_read_bytes Bytes read by the process (page-cache aware).",
        "# TYPE process_io_read_bytes gauge",
        f'process_io_read_bytes{{service="{SERVICE_NAME}"}} {int(p["process_io_read_bytes"])}',
        "# HELP process_io_write_bytes Bytes written by the process (page-cache aware).",
        "# TYPE process_io_write_bytes gauge",
        f'process_io_write_bytes{{service="{SERVICE_NAME}"}} {int(p["process_io_write_bytes"])}',
        "# HELP process_io_read_syscalls Number of read syscalls.",
        "# TYPE process_io_read_syscalls counter",
        f'process_io_read_syscalls{{service="{SERVICE_NAME}"}} {int(p["process_io_read_syscalls"])}',
        "# HELP process_io_write_syscalls Number of write syscalls.",
        "# TYPE process_io_write_syscalls counter",
        f'process_io_write_syscalls{{service="{SERVICE_NAME}"}} {int(p["process_io_write_syscalls"])}',
        "# HELP process_open_fds Number of open file descriptors.",
        "# TYPE process_open_fds gauge",
        f'process_open_fds{{service="{SERVICE_NAME}"}} {int(p["process_open_fds"])}',
        "# HELP process_threads Number of threads.",
        "# TYPE process_threads gauge",
        f'process_threads{{service="{SERVICE_NAME}"}} {int(p["process_threads"])}',
        "# HELP system_boot_time_seconds System boot time in seconds since unix epoch.",
        "# TYPE system_boot_time_seconds gauge",
        f'system_boot_time_seconds {boot:.3f}',
        "# HELP http_requests_total Total HTTP requests served.",
        "# TYPE http_requests_total counter",
    ]
    for code in sorted(_HTTP_BY_CODE):
        lines.append(f'http_requests_total{{service="{SERVICE_NAME}",code="{code}"}} {_HTTP_BY_CODE[code]}')
    lines.append(f'http_requests_total{{service="{SERVICE_NAME}",code="total"}} {_HTTP_TOTAL}')
    lines += [
        "# HELP http_requests_active Requests currently in flight.",
        "# TYPE http_requests_active gauge",
        f'http_requests_active{{service="{SERVICE_NAME}"}} {_HTTP_ACTIVE}',
        "# HELP http_requests_errors_total HTTP 5xx responses.",
        "# TYPE http_requests_errors_total counter",
        f'http_requests_errors_total{{service="{SERVICE_NAME}"}} {_HTTP_ERROR}',
        "# HELP webui_service_healthy Liveness: 1 if the process is serving normally.",
        "# TYPE webui_service_healthy gauge",
        f'webui_service_healthy{{service="{SERVICE_NAME}"}} {1 if _PROCESS_HEALTHY else 0}',
        "# HELP webui_service_ready Readiness: 1 if dependencies are satisfied.",
        "# TYPE webui_service_ready gauge",
        f'webui_service_ready{{service="{SERVICE_NAME}"}} {1 if _PROCESS_READY else 0}',
        f'python_info{{version="{platform.python_version()}"}} 1',
    ]
    return "\n".join(lines) + "\n"


def summarize(text):
    """Extract the nearest value for each metric name (labels ignored)."""
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "{" in line:
            name, _, rest = line.partition("{")
            tail = rest.rpartition("}")[2]
        else:
            parts = line.split()
            name = parts[0]
            tail = " ".join(parts[1:])
        if name not in out:
            try:
                out[name] = float(tail.strip())
            except ValueError:
                continue
    return out