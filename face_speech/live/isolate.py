"""Start the fixed research worker under a Windows AppContainer using standard handles."""

import ctypes as c
from ctypes import wintypes as w
import msvcrt
import os
from pathlib import Path
import subprocess
import sys

from _winapi import CloseHandle, TerminateProcess, WaitForSingleObject

PROFILE = "ASTRA.Research.Capture"
SIZE = c.c_size_t
PTR = c.c_void_p
kernel = c.WinDLL("kernel32", use_last_error=True)
user = c.WinDLL("userenv")
security = c.WinDLL("advapi32", use_last_error=True)


class Startup(c.Structure):
    _fields_ = [
        ("size", w.DWORD), ("reserved", w.LPWSTR), ("desktop", w.LPWSTR),
        ("title", w.LPWSTR), ("x", w.DWORD), ("y", w.DWORD), ("width", w.DWORD),
        ("height", w.DWORD), ("columns", w.DWORD), ("rows", w.DWORD), ("fill", w.DWORD),
        ("flags", w.DWORD), ("show", w.WORD), ("reserved_size", w.WORD), ("reserved_bytes", PTR),
        ("stdin", w.HANDLE), ("stdout", w.HANDLE), ("stderr", w.HANDLE), ("attributes", PTR),
    ]


class Capabilities(c.Structure):
    _fields_ = [("sid", PTR), ("entries", PTR), ("count", w.DWORD), ("reserved", w.DWORD)]


class Process(c.Structure):
    _fields_ = [("process", w.HANDLE), ("thread", w.HANDLE), ("pid", w.DWORD), ("tid", w.DWORD)]


class BasicLimits(c.Structure):
    _fields_ = [
        ("process_time", c.c_int64), ("job_time", c.c_int64), ("flags", w.DWORD),
        ("min_working_set", SIZE), ("max_working_set", SIZE), ("process_limit", w.DWORD),
        ("affinity", SIZE), ("priority", w.DWORD), ("scheduling", w.DWORD),
    ]


class ExtendedLimits(c.Structure):
    _fields_ = [("basic", BasicLimits), ("io", c.c_uint64 * 6), ("memory", SIZE * 4)]


def setup_signatures():
    user.CreateAppContainerProfile.argtypes = [w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, PTR, w.DWORD, c.POINTER(PTR)]
    user.DeriveAppContainerSidFromAppContainerName.argtypes = [w.LPCWSTR, c.POINTER(PTR)]
    security.ConvertSidToStringSidW.argtypes = [PTR, c.POINTER(w.LPWSTR)]
    security.FreeSid.argtypes = [PTR]
    kernel.LocalFree.argtypes = [PTR]
    kernel.InitializeProcThreadAttributeList.argtypes = [PTR, w.DWORD, w.DWORD, c.POINTER(SIZE)]
    kernel.UpdateProcThreadAttribute.argtypes = [PTR, w.DWORD, SIZE, PTR, SIZE, PTR, PTR]
    kernel.DeleteProcThreadAttributeList.argtypes = [PTR]
    kernel.CreateProcessW.argtypes = [
        w.LPCWSTR, w.LPWSTR, PTR, PTR, w.BOOL, w.DWORD, PTR, w.LPCWSTR,
        c.POINTER(Startup), c.POINTER(Process),
    ]
    kernel.CreateJobObjectW.argtypes = [PTR, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, PTR, w.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.ResumeThread.argtypes = [w.HANDLE]
    kernel.ResumeThread.restype = w.DWORD
    kernel.GetExitCodeProcess.argtypes = [w.HANDLE, c.POINTER(w.DWORD)]


def check(success):
    if not success:
        raise c.WinError(c.get_last_error())


def profile_sid():
    sid = PTR()
    result = user.CreateAppContainerProfile(PROFILE, "ASTRA Research", "Local research inference", None, 0, c.byref(sid))
    if result & 0xffffffff == 0x800700b7:
        result = user.DeriveAppContainerSidFromAppContainerName(PROFILE, c.byref(sid))
    if result:
        raise OSError(f"Could not create AppContainer profile: 0x{result & 0xffffffff:08x}")
    return sid


def run(sid, args, cwd):
    length = SIZE()
    kernel.InitializeProcThreadAttributeList(None, 2, 0, c.byref(length))
    attributes = c.create_string_buffer(length.value)
    check(kernel.InitializeProcThreadAttributeList(attributes, 2, 0, c.byref(length)))
    try:
        caps = Capabilities(sid, None, 0, 0)
        check(kernel.UpdateProcThreadAttribute(attributes, 0, 0x20009, c.byref(caps), c.sizeof(caps), None, None))

        handles = (w.HANDLE * 3)(*(msvcrt.get_osfhandle(i) for i in range(3)))
        for handle in handles:
            os.set_handle_inheritable(handle, True)
        check(kernel.UpdateProcThreadAttribute(attributes, 0, 0x20002, handles, c.sizeof(handles), None, None))
        startup = Startup(size=c.sizeof(Startup), flags=0x100, stdin=handles[0],
                          stdout=handles[1], stderr=handles[2], attributes=c.addressof(attributes))
        process = Process()
        command = c.create_unicode_buffer(subprocess.list2cmdline(args))
        environment = {
            "SYSTEMROOT": os.environ["SYSTEMROOT"],
            "PATH": os.pathsep.join([str(Path(args[0]).parent), os.environ["SYSTEMROOT"] + r"\System32"]),
            "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "1",
            "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        }
        for name in ("USERPROFILE", "LOCALAPPDATA", "APPDATA", "SYSTEMDRIVE", "PROGRAMDATA", "WINDIR", "PROCESSOR_ARCHITECTURE"):
            environment[name] = os.environ[name]
        environment["TEMP"] = environment["TMP"] = str(cwd)
        block = c.create_unicode_buffer("\0".join(f"{key}={value}" for key, value in sorted(environment.items())) + "\0")
        job = kernel.CreateJobObjectW(None, None)
        check(job)
        try:
            limits = ExtendedLimits()
            limits.basic.flags = 0x2000 | 0x8  # Kill on job close, one process.
            limits.basic.process_limit = 1
            check(kernel.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits)))
            flags = 0x80000 | 0x08000000 | 0x400 | 0x4  # Extended startup, hidden, Unicode, suspended.
            check(kernel.CreateProcessW(args[0], command, None, None, True, flags, block, str(cwd), c.byref(startup), c.byref(process)))
            try:
                if not kernel.AssignProcessToJobObject(job, process.process):
                    error = c.get_last_error()
                    TerminateProcess(process.process, 1)
                    raise c.WinError(error)
                check(kernel.ResumeThread(process.thread) != 0xffffffff)
                WaitForSingleObject(process.process, 0xffffffff)
                code = w.DWORD()
                check(kernel.GetExitCodeProcess(process.process, c.byref(code)))
                return code.value
            finally:
                CloseHandle(process.thread)
                CloseHandle(process.process)
        finally:
            CloseHandle(job)
    finally:
        kernel.DeleteProcThreadAttributeList(attributes)


if __name__ == "__main__":
    setup_signatures()
    sid = profile_sid()
    try:
        if sys.argv[1:] == ["--sid"]:
            value = w.LPWSTR()
            check(security.ConvertSidToStringSidW(sid, c.byref(value)))
            try:
                print(value.value)
            finally:
                kernel.LocalFree(value)
        else:
            # The venv's Windows redirector would spawn another process. Run the
            # base interpreter and add the reviewed venv to sys.path in worker.py.
            path = Path(sys.argv[1]).resolve(strict=True)
            root = path.parent
            raise SystemExit(run(sid, [sys._base_executable, "-I", "-B", str(path), *sys.argv[2:]], root))
    finally:
        security.FreeSid(sid)
