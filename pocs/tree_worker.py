"""Worker for P2-TREE-01. Windows + Python 3.10 + pywin32."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

import win32api
import win32con
import win32job
import win32event
import win32process

KILL_ON_JOB_CLOSE = 0x00002000


def create_guard_job():
    job = win32job.CreateJobObject(None, f"ForgeTreeGuardian_{os.getpid()}_{time.time_ns()}")
    info = win32job.QueryInformationJobObject(
        job, win32job.JobObjectExtendedLimitInformation
    )
    info["BasicLimitInformation"]["LimitFlags"] |= KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(
        job, win32job.JobObjectExtendedLimitInformation, info
    )
    return job


def create_child(level: int, args, *, breakaway: bool = False):
    script = os.path.abspath(__file__)
    command = (
        f'"{sys.executable}" "{script}" --run-id={args.run_id} '
        f"--level={level} --max={args.max} --controller-pid={args.controller_pid}"
    )
    if breakaway:
        command += " --breakaway-child"
    flags = getattr(subprocess, "CREATE_SUSPENDED", 0x00000004)
    if breakaway:
        flags |= getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)
    si = __import__("win32process").STARTUPINFO()
    import win32process
    return win32process.CreateProcess(
        None, command, None, None, False, flags, None, None, si
    )


def report_alive(args):
    folder = os.path.join(os.path.dirname(__file__), f".tree_reports_{args.run_id}")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"report_{args.level}.json")
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as stream:
        json.dump({"pid": os.getpid(), "level": args.level}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--level", type=int, default=0)
    parser.add_argument("--max", type=int, default=2)
    parser.add_argument("--controller-pid", type=int, required=True)
    parser.add_argument("--breakaway-child", action="store_true")
    parser.add_argument("--scenario-d", action="store_true")
    args = parser.parse_args()
    report_alive(args)

    if args.breakaway_child:
        # The child is intentionally inert; the controller terminates it by handle.
        while True:
            time.sleep(1)

    if args.level < args.max:
        if args.scenario_d:
            # D expects ERROR_ACCESS_DENIED because this Job disallows
            # breakaway. If creation unexpectedly succeeds, immediately place
            # the still-suspended child in a private kill-on-close guardian.
            # The guardian handle is owned by this worker: terminating the
            # worker closes its last handle and kills the child as well.
            guardian = create_guard_job()
            h_process = h_thread = None
            assigned = False
            try:
                try:
                    h_process, h_thread, child_pid, _ = create_child(
                        args.level + 1, args, breakaway=True
                    )
                except Exception as exc:
                    if getattr(exc, "winerror", None) == 5:
                        print("[WORKER] Breakaway denied with ERROR_ACCESS_DENIED", flush=True)
                        return
                    raise

                try:
                    win32job.AssignProcessToJobObject(guardian, h_process)
                    assigned = True
                    win32process.ResumeThread(h_thread)
                    win32event.WaitForSingleObject(h_process, win32event.INFINITE)
                except Exception:
                    # If guardian assignment failed, explicitly kill the
                    # suspended child; closing an empty guardian cannot do it.
                    if not assigned:
                        try:
                            win32api.TerminateProcess(h_process, 78)
                            win32event.WaitForSingleObject(h_process, 5000)
                        except Exception:
                            pass
                    raise
            finally:
                if h_thread:
                    win32api.CloseHandle(h_thread)
                if h_process:
                    win32api.CloseHandle(h_process)
                win32api.CloseHandle(guardian)
            return

        # Ordinary descendants inherit the parent's Job membership atomically
        # at process creation. The controller discovers them from Job PID list;
        # no PID handoff is required for A/B/C.
        import win32process
        h_process, h_thread, child_pid, _ = create_child(args.level + 1, args)
        win32process.ResumeThread(h_thread)
        win32api.CloseHandle(h_thread)
        win32api.CloseHandle(h_process)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()