"""Windows Job Objects for the processes the service starts: the Windows stand-in for process groups and for
sandbox-exec's process rules (Windows only).

A child starts suspended, joins its own job and only then runs, so neither it nor what it starts can leave the job
unless the launch allows it. Ending the job, or closing its last handle when the service dies, ends them all. The
process count limit is the "no other programs" rule; file access is not restricted on Windows.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import socket
import subprocess
import time

from .host import Confined

CREATE_SUSPENDED = 0x00000004
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000

_LIMIT_PROCESS_TIME = 0x00000002
_LIMIT_ACTIVE_PROCESS = 0x00000008
_LIMIT_PROCESS_MEMORY = 0x00000100
_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
_LIMIT_SILENT_BREAKAWAY_OK = 0x00001000
_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_BASIC_ACCOUNTING = 1
_PROCESS_ID_LIST = 3
_EXTENDED_LIMIT = 9
_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
_ERROR_ACCESS_DENIED = 5
_ERROR_INSUFFICIENT_BUFFER = 122
_TCP_TABLE_OWNER_PID_LISTENER = 3
_MAX_PIDS = 64


class _BasicLimit(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount",
                "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _ExtendedLimit(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimit), ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class _Accounting(ctypes.Structure):
    _fields_ = [("TotalUserTime", ctypes.c_int64), ("TotalKernelTime", ctypes.c_int64),
                ("ThisPeriodTotalUserTime", ctypes.c_int64), ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
                ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]


class _ProcessIds(ctypes.Structure):
    _fields_ = [("NumberOfAssignedProcesses", wintypes.DWORD), ("NumberOfProcessIdsInList", wintypes.DWORD),
                ("ProcessIdList", ctypes.c_size_t * _MAX_PIDS)]


class _MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                             "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                             "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_ntdll = ctypes.WinDLL("ntdll")
_iphlpapi = ctypes.WinDLL("iphlpapi")


def _function(library, name, result, *arguments):
    function = getattr(library, name)
    function.restype, function.argtypes = result, arguments
    return function


_CreateJobObject = _function(_kernel32, "CreateJobObjectW", wintypes.HANDLE, wintypes.LPVOID, wintypes.LPCWSTR)
_SetInformationJobObject = _function(_kernel32, "SetInformationJobObject", wintypes.BOOL, wintypes.HANDLE,
                                     ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
_QueryInformationJobObject = _function(_kernel32, "QueryInformationJobObject", wintypes.BOOL, wintypes.HANDLE,
                                       ctypes.c_int, wintypes.LPVOID, wintypes.DWORD, wintypes.LPDWORD)
_AssignProcessToJobObject = _function(_kernel32, "AssignProcessToJobObject", wintypes.BOOL, wintypes.HANDLE,
                                      wintypes.HANDLE)
_TerminateJobObject = _function(_kernel32, "TerminateJobObject", wintypes.BOOL, wintypes.HANDLE, wintypes.UINT)
_CloseHandle = _function(_kernel32, "CloseHandle", wintypes.BOOL, wintypes.HANDLE)
_OpenProcess = _function(_kernel32, "OpenProcess", wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_GetExitCodeProcess = _function(_kernel32, "GetExitCodeProcess", wintypes.BOOL, wintypes.HANDLE, wintypes.LPDWORD)
_QueryFullProcessImageName = _function(_kernel32, "QueryFullProcessImageNameW", wintypes.BOOL, wintypes.HANDLE,
                                       wintypes.DWORD, wintypes.LPWSTR, wintypes.LPDWORD)
_GetProcessMemoryInfo = _function(_kernel32, "K32GetProcessMemoryInfo", wintypes.BOOL, wintypes.HANDLE,
                                  ctypes.POINTER(_MemoryCounters), wintypes.DWORD)
_NtResumeProcess = _function(_ntdll, "NtResumeProcess", ctypes.c_long, wintypes.HANDLE)
_GetExtendedTcpTable = _function(_iphlpapi, "GetExtendedTcpTable", wintypes.DWORD, wintypes.LPVOID,
                                 wintypes.LPDWORD, wintypes.BOOL, wintypes.ULONG, ctypes.c_int, wintypes.ULONG)


def _check(succeeded) -> None:
    if not succeeded:
        raise ctypes.WinError(ctypes.get_last_error())


class Job:
    def __init__(self, limits: Confined):
        handle = _CreateJobObject(None, None)
        _check(handle)
        self.handle: int | None = handle
        info = _ExtendedLimit()
        basic = info.BasicLimitInformation
        basic.LimitFlags = _LIMIT_KILL_ON_JOB_CLOSE | _LIMIT_DIE_ON_UNHANDLED_EXCEPTION | _LIMIT_ACTIVE_PROCESS
        basic.ActiveProcessLimit = 1 + limits.children
        if limits.breakaway:
            basic.LimitFlags |= _LIMIT_SILENT_BREAKAWAY_OK
        if limits.memory is not None:
            basic.LimitFlags |= _LIMIT_PROCESS_MEMORY
            info.ProcessMemoryLimit = limits.memory
        if limits.cpu_seconds is not None:
            basic.LimitFlags |= _LIMIT_PROCESS_TIME
            basic.PerProcessUserTimeLimit = limits.cpu_seconds * 10_000_000
        try:
            _check(_SetInformationJobObject(handle, _EXTENDED_LIMIT, ctypes.byref(info), ctypes.sizeof(info)))
        except OSError:
            self.close()
            raise

    def assign(self, process: subprocess.Popen) -> None:
        _check(_AssignProcessToJobObject(self.handle, int(process._handle)))

    def active(self) -> int:
        info = _Accounting()
        _check(_QueryInformationJobObject(self.handle, _BASIC_ACCOUNTING, ctypes.byref(info), ctypes.sizeof(info),
                                          None))
        return info.ActiveProcesses

    def pids(self) -> list[int]:
        info = _ProcessIds()
        _check(_QueryInformationJobObject(self.handle, _PROCESS_ID_LIST, ctypes.byref(info), ctypes.sizeof(info),
                                          None))
        return [int(info.ProcessIdList[index]) for index in range(info.NumberOfProcessIdsInList)]

    def terminate(self) -> None:
        _check(_TerminateJobObject(self.handle, 1))

    def close(self) -> None:
        if self.handle is not None:
            _CloseHandle(self.handle)
            self.handle = None


def spawn(arguments: list[str], limits: Confined, **popen) -> subprocess.Popen:
    """Popen whose process runs only inside its own job, kept as `process.foldcv_job`; no console window."""
    job = Job(limits)
    try:
        process = subprocess.Popen(arguments, creationflags=CREATE_SUSPENDED | CREATE_NEW_PROCESS_GROUP
                                   | CREATE_NO_WINDOW, **popen)
    except BaseException:
        job.close()
        raise
    try:
        job.assign(process)
        status = _NtResumeProcess(int(process._handle))
        if status < 0:
            raise OSError(f"NtResumeProcess failed: {status & 0xFFFFFFFF:#010x}")
    except BaseException:
        job.close()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        raise
    process.foldcv_job = job
    return process


def stop(process: subprocess.Popen, *, timeout: float = 1.5) -> bool:
    """End the process and all that is left in its job; False when something is still running at the timeout."""
    job: Job | None = getattr(process, "foldcv_job", None)
    if job is None or job.handle is None:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=timeout)
        return True
    try:
        job.terminate()
        deadline = time.monotonic() + timeout
        while job.active():
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)
        process.wait(timeout=timeout)
        return True
    finally:
        job.close()


def job_pids(process: subprocess.Popen) -> list[int]:
    """Every process in the child's job, the child included."""
    job: Job | None = getattr(process, "foldcv_job", None)
    if job is None or job.handle is None:
        raise OSError("The process has no job")
    return job.pids()


def process_alive(pid: int) -> bool:
    handle = _OpenProcess(_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        # A protected process denies the query but exists.
        return ctypes.get_last_error() == _ERROR_ACCESS_DENIED
    try:
        code = wintypes.DWORD()
        return bool(_GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == _STILL_ACTIVE
    finally:
        _CloseHandle(handle)


def image(pid: int) -> str | None:
    """The full path of a process's executable."""
    handle = _OpenProcess(_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        return buffer.value if _QueryFullProcessImageName(handle, 0, buffer, ctypes.byref(size)) else None
    finally:
        _CloseHandle(handle)


def working_set_kb(process: subprocess.Popen) -> int | None:
    counters = _MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not _GetProcessMemoryInfo(int(process._handle), ctypes.byref(counters), counters.cb):
        return None
    return counters.WorkingSetSize // 1024


def listening_pids() -> set[int]:
    """Owners of listening TCP sockets, IPv4 and IPv6."""
    owners: set[int] = set()
    # Row sizes and the owning PID's offset: MIB_TCPROW_OWNER_PID and MIB_TCP6ROW_OWNER_PID.
    for family, row, pid_offset in ((socket.AF_INET, 24, 20), (socket.AF_INET6, 56, 52)):
        size = wintypes.DWORD(0)
        buffer = None
        for _ in range(8):
            buffer = ctypes.create_string_buffer(size.value or 1)
            result = _GetExtendedTcpTable(buffer, ctypes.byref(size), False, family, _TCP_TABLE_OWNER_PID_LISTENER, 0)
            if result == 0:
                break
            if result != _ERROR_INSUFFICIENT_BUFFER:
                raise ctypes.WinError(result)
        else:
            raise OSError("The TCP table kept growing")
        count = int.from_bytes(buffer.raw[:4], "little")
        for index in range(count):
            start = 4 + index * row + pid_offset
            owners.add(int.from_bytes(buffer.raw[start:start + 4], "little"))
    return owners
