"""P2-TREE-01: Windows Job Object process-tree containment PoC.

This is a standalone PoC. It does not import FORGE Core or alter Phase 1.
Run on the target Windows host; runtime behavior is intentionally not claimed here.
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import time
import uuid
from ctypes import wintypes

import pywintypes
import win32api
import win32con
import win32event
import win32file
import win32job
import win32pipe
import win32process

KILL_ON_JOB_CLOSE = 0x00002000
SCENARIO_TIMEOUT = 30.0
CLEANUP_TIMEOUT = 10.0


class PROCESS_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("ExitStatus", wintypes.LONG),
        ("PebBaseAddress", ctypes.c_void_p),
        ("AffinityMask", ctypes.c_size_t),
        ("BasePriority", ctypes.c_long),
        ("UniqueProcessId", ctypes.c_size_t),
        ("InheritedFromUniqueProcessId", ctypes.c_size_t),
    ]


def ppid_of(handle) -> int | None:
    pbi = PROCESS_BASIC_INFORMATION()
    returned = wintypes.ULONG()
    ntdll = ctypes.WinDLL("ntdll")
    query = ntdll.NtQueryInformationProcess
    query.argtypes = [ctypes.c_void_p, wintypes.ULONG, ctypes.c_void_p,
                      wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)]
    query.restype = wintypes.LONG
    status = query(int(handle), 0, ctypes.byref(pbi), ctypes.sizeof(pbi),
                   ctypes.byref(returned))
    if status != 0:
        return None
    return int(pbi.InheritedFromUniqueProcessId)


def make_job():
    job = win32job.CreateJobObject(None, f"ForgeTreePoC_{uuid.uuid4().hex}")
    info = win32job.QueryInformationJobObject(
        job, win32job.JobObjectExtendedLimitInformation
    )
    info["BasicLimitInformation"]["LimitFlags"] |= KILL_ON_JOB_CLOSE
    # Deliberately DO NOT set BREAKAWAY_OK or SILENT_BREAKAWAY_OK.
    win32job.SetInformationJobObject(
        job, win32job.JobObjectExtendedLimitInformation, info
    )
    return job


def job_pids(job) -> set[int]:
    """PyWin32 returns a sequence of PIDs for BasicProcessIdList (not a dict).

    Other Job information classes return dictionaries. Keep this adapter
    explicit so a PyWin32 tuple/sequence is never indexed by a string key.
    """
    result = win32job.QueryInformationJobObject(
        job, win32job.JobObjectBasicProcessIdList
    )
    if isinstance(result, dict):
        # Defensive compatibility for wrappers that expose the native fields.
        values = result.get("ProcessIdList")
        if values is None:
            raise RuntimeError(
                "Unexpected JobObjectBasicProcessIdList dictionary shape"
            )
    elif isinstance(result, (tuple, list)):
        values = result
    else:
        raise TypeError(
            "Unexpected JobObjectBasicProcessIdList result type: "
            f"{type(result).__name__}"
        )
    return {int(pid) for pid in values}


def spawn_worker(run_id: str, max_level: int, *, scenario_d=False):
    worker = os.path.join(os.path.dirname(__file__), "tree_worker.py")
    cmd = (f'"{sys.executable}" "{worker}" --run-id={run_id} '
           f"--level=0 --max={max_level} --controller-pid={os.getpid()}")
    if scenario_d:
        cmd += " --scenario-d"
    startup = win32process.STARTUPINFO()
    return win32process.CreateProcess(
        None, cmd, None, None, False, win32process.CREATE_SUSPENDED,
        None, os.path.dirname(worker), startup
    )


def wait_exact(job, expected_count: int, deadline: float) -> set[int] | None:
    """Wait for an exact count, then require the same PID set twice."""
    previous = None
    stable_samples = 0
    while time.monotonic() < deadline:
        current = job_pids(job)
        if len(current) == expected_count:
            if current == previous:
                stable_samples += 1
            else:
                stable_samples = 1
            if stable_samples >= 3:
                return current
        else:
            stable_samples = 0
        previous = current
        time.sleep(0.15)
    return None


def open_process(pid: int):
    access = (win32con.SYNCHRONIZE | win32con.PROCESS_QUERY_INFORMATION |
              win32con.PROCESS_TERMINATE)
    return win32api.OpenProcess(access, False, pid)


def wait_dead(handle, deadline: float) -> bool:
    remaining = max(0.0, deadline - time.monotonic())
    ms = min(int(remaining * 1000), 0xFFFFFFFE)
    return win32event.WaitForSingleObject(handle, ms) == win32con.WAIT_OBJECT_0


def cleanup(job, handles, threads) -> tuple[bool, list]:
    deadline = time.monotonic() + CLEANUP_TIMEOUT
    if job:
        try:
            win32job.TerminateJobObject(job, 77)
        except Exception as exc:
            print(f"[CLEANUP] TerminateJobObject: {exc}")
    survivors = []
    for handle in handles:
        try:
            if not wait_dead(handle, deadline):
                try:
                    win32api.TerminateProcess(handle, 77)
                except Exception:
                    pass
                if not wait_dead(handle, deadline):
                    survivors.append(handle)
                    print(f"[ORPHAN_UNCONFIRMED] PID={win32process.GetProcessId(handle)}")
                    continue
            win32api.CloseHandle(handle)
        except Exception as exc:
            survivors.append(handle)
            print(f"[ORPHAN_UNCONFIRMED] Handle cleanup error: {exc}")
    for handle in threads:
        try:
            win32api.CloseHandle(handle)
        except Exception:
            pass
    if job:
        try:
            win32api.CloseHandle(job)
        except Exception:
            pass
    return not survivors, survivors


def run_tree_scenario(label: str, depth: int) -> bool:
    print(f"\n=== SCENARIO {label}: TREE DEPTH {depth} ===")
    run_id = uuid.uuid4().hex[:10]
    job = None
    process_handles = []
    thread_handles = []
    passed = False
    try:
        job = make_job()
        hp, ht, worker_pid, _ = spawn_worker(run_id, depth - 1)
        process_handles.append(hp)
        thread_handles.append(ht)
        win32job.AssignProcessToJobObject(job, hp)
        win32process.ResumeThread(ht)

        deadline = time.monotonic() + SCENARIO_TIMEOUT
        pids = wait_exact(job, depth, deadline)
        if pids is None:
            print(f"[FAIL] Expected exactly {depth} Job members; got {job_pids(job)}")
        else:
            by_pid = {pid: open_process(pid) for pid in pids if pid != worker_pid}
            process_handles.extend(by_pid.values())
            expected_chain = sorted(pids, key=lambda pid: _level_from_report(run_id, pid))
            # Reports carry level numbers; verify the full parent chain.
            levels = sorted(((_level_from_report(run_id, pid), pid) for pid in pids))
            chain_ok = True
            for index in range(1, len(levels)):
                child_pid = levels[index][1]
                parent_pid = levels[index - 1][1]
                hchild = by_pid.get(child_pid)
                if hchild is None or ppid_of(hchild) != parent_pid:
                    chain_ok = False
                    break
            membership_ok = all(win32job.IsProcessInJob(h, job) for h in process_handles)
            if chain_ok and membership_ok and len(expected_chain) == depth:
                print(f"[PASS] Exact Job PID set and PPID chain verified: {sorted(pids)}")
                passed = True
            else:
                print(f"[FAIL] PPID/membership verification failed. PIDs={sorted(pids)}")
    except Exception as exc:
        print(f"[ERROR] Scenario {label}: {type(exc).__name__}: {exc}")
    finally:
        clean, survivors = cleanup(job, process_handles, thread_handles)
    return passed and clean


def _level_from_report(run_id: str, pid: int) -> int:
    folder = os.path.join(os.path.dirname(__file__), f".tree_reports_{run_id}")
    for level in range(0, 4):
        path = os.path.join(folder, f"report_{level}.json")
        try:
            with open(path, "r", encoding="utf-8") as stream:
                item = json.load(stream)
            if int(item["pid"]) == pid:
                return int(item["level"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    raise RuntimeError(f"No level report for PID {pid}")


def run_termination_scenario() -> bool:
    print("\n=== SCENARIO C: TERMINATE JOB OBJECT ===")
    run_id = uuid.uuid4().hex[:10]
    job = None
    handles = []
    threads = []
    passed = False
    try:
        job = make_job()
        hp, ht, worker_pid, _ = spawn_worker(run_id, 2)
        handles.append(hp)
        threads.append(ht)
        win32job.AssignProcessToJobObject(job, hp)
        win32process.ResumeThread(ht)
        pids = wait_exact(job, 3, time.monotonic() + SCENARIO_TIMEOUT)
        if pids is None:
            print("[FAIL] Could not observe exactly three Job members")
        else:
            handles.extend(open_process(pid) for pid in pids if pid != worker_pid)
            win32job.TerminateJobObject(job, 456)
            deadline = time.monotonic() + SCENARIO_TIMEOUT
            all_dead = all(wait_dead(h, deadline) for h in handles)
            codes = [win32process.GetExitCodeProcess(h) for h in handles]
            active = win32job.QueryInformationJobObject(
                job, win32job.JobObjectBasicAndIoAccountingInformation
            )["BasicInfo"]["ActiveProcesses"]
            passed = all_dead and active == 0 and all(code == 456 for code in codes)
            print(f"[{'PASS' if passed else 'FAIL'}] signaled={all_dead}, exit_codes={codes}, ActiveProcesses={active}")
    except Exception as exc:
        print(f"[ERROR] Scenario C: {type(exc).__name__}: {exc}")
    finally:
        clean, _ = cleanup(job, handles, threads)
    return passed and clean


def run_breakaway_scenario() -> bool:
    """Attempt breakaway from a Job that explicitly disallows it.

    This test intentionally expects CreateProcess(CREATE_BREAKAWAY_FROM_JOB)
    to fail with ERROR_ACCESS_DENIED. It does not claim to test successful
    escape from every enclosing/nested Job.
    """
    print("\n=== SCENARIO D: BREAKAWAY DENIAL ===")
    run_id = uuid.uuid4().hex[:10]
    job = None
    handles = []
    threads = []
    passed = False
    try:
        job = make_job()
        hp, ht, worker_pid, _ = spawn_worker(run_id, 1, scenario_d=True)
        handles.append(hp)
        threads.append(ht)
        win32job.AssignProcessToJobObject(job, hp)
        win32process.ResumeThread(ht)
        deadline = time.monotonic() + SCENARIO_TIMEOUT
        while time.monotonic() < deadline:
            code = win32process.GetExitCodeProcess(hp)
            if code != win32con.STILL_ACTIVE:
                break
            time.sleep(0.1)
        code = win32process.GetExitCodeProcess(hp)
        # Worker exits 0 only when OS rejects breakaway with ACCESS_DENIED.
        passed = code == 0
        print(f"[{'PASS' if passed else 'FAIL'}] Worker exit code={code}; expected 0 after ERROR_ACCESS_DENIED")
    except Exception as exc:
        print(f"[ERROR] Scenario D: {type(exc).__name__}: {exc}")
    finally:
        clean, _ = cleanup(job, handles, threads)
    return passed and clean


def main() -> int:
    if os.name != "nt":
        print("This PoC requires Windows.")
        return 2
    print("P2-TREE-01 — PROCESS TREE CONTAINMENT")
    results = {
        "A": run_tree_scenario("A", 2),
        "B": run_tree_scenario("B", 3),
        "C": run_termination_scenario(),
        "D": run_breakaway_scenario(),
    }
    print("\n=== SUMMARY ===")
    for name, result in results.items():
        print(f"Scenario {name}: {'PASS' if result else 'FAIL'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())