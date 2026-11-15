"""P2-RT-01: Restricted Token Windows security PoC.

Requires Windows, Python 3.10+, and pywin32. This is a standalone PoC;
it does not import or modify FORGE Core.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

import win32api
import win32con
import win32event
import win32process
import win32security

DISABLE_MAX_PRIVILEGE = 0x1
INTERACTIVE_SID = "S-1-5-4"
WAIT_TIMEOUT_MS = 30_000


def sid_text(sid) -> str:
    return win32security.ConvertSidToStringSid(sid)


def token_snapshot(token) -> dict:
    """Return auditable token properties without exposing account names."""
    user_info = win32security.GetTokenInformation(token, win32security.TokenUser)
    user_sid = user_info[0]
    groups_info = win32security.GetTokenInformation(token, win32security.TokenGroups)
    groups = []
    for sid, attrs in groups_info:
        groups.append({"sid": sid_text(sid), "attributes": int(attrs)})

    privileges_info = win32security.GetTokenInformation(token, win32security.TokenPrivileges)
    privileges = []
    for luid, attrs in privileges_info:
        try:
            name = win32security.LookupPrivilegeName(None, luid)
        except Exception:
            name = str(luid)
        privileges.append({"name": name, "attributes": int(attrs)})

    restricted_info = win32security.GetTokenInformation(token, win32security.TokenRestrictedSids)
    restricted_sids = [sid_text(item[0]) for item in restricted_info]
    interactive_group_deny_only = any(
        sid_text(sid) == INTERACTIVE_SID and (attrs & win32security.SE_GROUP_USE_FOR_DENY_ONLY)
        for sid, attrs in groups_info
    )
    integrity_info = win32security.GetTokenInformation(token, win32security.TokenIntegrityLevel)
    integrity_sid = integrity_info[0]
    integrity = sid_text(integrity_sid)

    def scalar(info_class, default=None):
        try:
            value = win32security.GetTokenInformation(token, info_class)
            if isinstance(value, tuple) and len(value) == 1:
                value = value[0]
            return int(value)
        except Exception:
            return default

    enabled_privileges = [
        p["name"] for p in privileges
        if p["attributes"] & win32security.SE_PRIVILEGE_ENABLED
    ]
    return {
        "user_sid": sid_text(user_sid),
        "groups": groups,
        "privileges": privileges,
        "enabled_privileges": enabled_privileges,
        "restricted_sids": restricted_sids,
        "is_token_restricted": bool(win32security.IsTokenRestricted(token)),
        "interactive_group_deny_only": interactive_group_deny_only,
        "elevation_type": scalar(getattr(win32security, "TokenElevationType", 18)),
        "integrity_sid": integrity,
        "ui_access": scalar(getattr(win32security, "TokenUIAccess", 26)),
        "is_app_container": scalar(getattr(win32security, "TokenIsAppContainer", 29)),
    }


def set_file_sddl(path: str, sddl: str) -> None:
    sd = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
        sddl, win32security.SDDL_REVISION_1
    )
    dacl = sd.GetSecurityDescriptorDacl()
    security_info = win32security.DACL_SECURITY_INFORMATION | 0x80000000  # PROTECTED_DACL_SECURITY_INFORMATION
    # PyWin32 converts this argument through a signed C long. Preserve the
    # SECURITY_INFORMATION DWORD bit pattern without overflowing C long.
    if security_info >= 0x80000000:
        security_info -= 0x100000000
    win32security.SetNamedSecurityInfo(
        path,
        win32security.SE_FILE_OBJECT,
        security_info,
        None,
        None,
        dacl,
        None,
    )


def can_read(path: str) -> tuple[bool, str | None]:
    try:
        with open(path, "rb") as stream:
            stream.read(1)
        return True, None
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"


def write_json(path: str, data: dict) -> None:
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def worker_main(args) -> int:
    role = args.role
    token = win32security.OpenProcessToken(
        win32process.GetCurrentProcess(), win32security.TOKEN_QUERY
    )
    snapshot = token_snapshot(token)
    win32api.CloseHandle(token)

    protected_ok, protected_error = can_read(args.protected_file)
    allowed_ok, allowed_error = can_read(args.allowed_file)
    result = {
        "role": role,
        "pid": os.getpid(),
        "token": snapshot,
        "filesystem": {
            "protected_file_read": protected_ok,
            "protected_file_error": protected_error,
            "allowed_workspace_file_read": allowed_ok,
            "allowed_workspace_file_error": allowed_error,
        },
    }
    write_json(args.report, result)

    if role == "worker":
        command = subprocess.list2cmdline([
            sys.executable, os.path.abspath(__file__),
            "--role", "child",
            "--protected-file", args.protected_file,
            "--allowed-file", args.allowed_file,
            "--report", args.child_report,
        ])
        startup = win32process.STARTUPINFO()
        hp = ht = None
        try:
            hp, ht, _, _ = win32process.CreateProcess(
                None, command, None, None, False, win32process.CREATE_NO_WINDOW,
                None, os.path.dirname(os.path.abspath(__file__)), startup,
            )
            win32api.CloseHandle(ht)
            ht = None
            wait = win32event.WaitForSingleObject(hp, WAIT_TIMEOUT_MS)
            if wait != win32con.WAIT_OBJECT_0:
                win32api.TerminateProcess(hp, 124)
                win32event.WaitForSingleObject(hp, 5000)
                return 124
            child_exit = win32process.GetExitCodeProcess(hp)
            result["child_exit_code"] = int(child_exit)
            write_json(args.report, result)
            return int(child_exit)
        finally:
            if ht:
                win32api.CloseHandle(ht)
            if hp:
                win32api.CloseHandle(hp)

    return 0


def create_test_files(root: str) -> tuple[str, str, str]:
    user_token = win32security.OpenProcessToken(
        win32process.GetCurrentProcess(), win32security.TOKEN_QUERY
    )
    try:
        user_sid = win32security.GetTokenInformation(user_token, win32security.TokenUser)[0]
        token_groups = win32security.GetTokenInformation(user_token, win32security.TokenGroups)
        interactive_enabled = any(
            sid_text(sid) == INTERACTIVE_SID and (attrs & win32security.SE_GROUP_ENABLED)
            for sid, attrs in token_groups
        )
    finally:
        win32api.CloseHandle(user_token)
    user_sid_s = sid_text(user_sid)
    if not interactive_enabled:
        raise RuntimeError("Current token does not contain an enabled INTERACTIVE SID; PoC will not substitute a broader group.")

    protected = os.path.join(root, "protected_interactive_only.txt")
    allowed = os.path.join(root, "workspace_user_sid.txt")
    Path(protected).write_text("protected test data\n", encoding="utf-8")
    Path(allowed).write_text("approved workspace test data\n", encoding="utf-8")

    # The original token receives access through INTERACTIVE. The restricted
    # token changes that group to deny-only, so it cannot grant this ACE.
    set_file_sddl(protected, f"D:P(A;;FR;;;{INTERACTIVE_SID})")
    set_file_sddl(allowed, f"D:P(A;;FR;;;{user_sid_s})")
    return protected, allowed, user_sid_s


def launch_restricted_worker(protected: str, allowed: str, report: str, child_report: str):
    current = win32security.OpenProcessToken(
        win32process.GetCurrentProcess(),
        win32security.TOKEN_QUERY | win32security.TOKEN_DUPLICATE | win32security.TOKEN_ASSIGN_PRIMARY,
    )
    interactive_sid = win32security.ConvertStringSidToSid(INTERACTIVE_SID)
    restricted_token = None
    hp = ht = None
    try:
        restricted_token = win32security.CreateRestrictedToken(
            current,
            DISABLE_MAX_PRIVILEGE,
            ((interactive_sid, 0),),
            None,
            None,
        )
        command = subprocess.list2cmdline([
            sys.executable, os.path.abspath(__file__),
            "--role", "worker",
            "--protected-file", protected,
            "--allowed-file", allowed,
            "--report", report,
            "--child-report", child_report,
        ])
        startup = win32process.STARTUPINFO()
        try:
            hp, ht, pid, _ = win32process.CreateProcessAsUser(
                restricted_token,
                sys.executable,
                command,
                None,
                None,
                False,  # never inherit controller handles
                win32process.CREATE_NO_WINDOW,
                None,
                os.path.dirname(os.path.abspath(__file__)),
                startup,
            )
        except Exception as exc:
            winerror = getattr(exc, "winerror", None)
            raise RuntimeError(
                "CreateProcessAsUser failed. No privilege elevation or fallback "
                "to an unrestricted token is attempted. Check the reported "
                f"Windows error and caller token privileges. winerror={winerror}; {exc}"
            ) from exc
        win32api.CloseHandle(ht)
        ht = None
        wait = win32event.WaitForSingleObject(hp, WAIT_TIMEOUT_MS)
        if wait != win32con.WAIT_OBJECT_0:
            win32api.TerminateProcess(hp, 124)
            win32event.WaitForSingleObject(hp, 5000)
            raise TimeoutError("Restricted Worker did not exit before timeout")
        exit_code = win32process.GetExitCodeProcess(hp)
        return int(pid), int(exit_code)
    finally:
        if ht:
            win32api.CloseHandle(ht)
        if hp:
            win32api.CloseHandle(hp)
        if restricted_token:
            win32api.CloseHandle(restricted_token)
        win32api.CloseHandle(current)


def controller_main() -> int:
    if os.name != "nt":
        print("P2-RT-01 requires Windows.")
        return 2
    root = tempfile.mkdtemp(prefix="forge_p2_rt_01_")
    protected, allowed, user_sid = create_test_files(root)
    report = os.path.join(root, "worker_report.json")
    child_report = os.path.join(root, "child_report.json")
    print("P2-RT-01 — RESTRICTED TOKEN PoC")
    print(f"Temporary test directory: {root}")
    print("[INFO] Creating a restricted primary token from the current user token.")
    try:
        pid, exit_code = launch_restricted_worker(protected, allowed, report, child_report)
        worker = json.loads(Path(report).read_text(encoding="utf-8"))
        child = json.loads(Path(child_report).read_text(encoding="utf-8"))
        baseline_protected, _ = can_read(protected)
        baseline_allowed, _ = can_read(allowed)

        checks = {
            "baseline_user_can_read_protected": baseline_protected,
            "baseline_user_can_read_workspace": baseline_allowed,
            "worker_interactive_sid_is_deny_only": worker["token"]["interactive_group_deny_only"],
            "worker_privileges_reduced": set(worker["token"]["enabled_privileges"]).issubset({"SeChangeNotifyPrivilege"}),
            "worker_protected_read_denied": not worker["filesystem"]["protected_file_read"],
            "worker_workspace_read_allowed": worker["filesystem"]["allowed_workspace_file_read"],
            "worker_exit_zero": exit_code == 0,
            "child_interactive_sid_is_deny_only": child["token"]["interactive_group_deny_only"],
            "child_privileges_reduced": set(child["token"]["enabled_privileges"]).issubset({"SeChangeNotifyPrivilege"}),
            "child_protected_read_denied": not child["filesystem"]["protected_file_read"],
            "child_workspace_read_allowed": child["filesystem"]["allowed_workspace_file_read"],
        }
        print(f"[INFO] Worker PID={pid}, exit_code={exit_code}")
        for name, passed in checks.items():
            print(f"[{ 'PASS' if passed else 'FAIL' }] {name}")
        print("\n[DETAIL] Worker token:")
        print(json.dumps(worker["token"], indent=2))
        print("\n[DETAIL] Child token:")
        print(json.dumps(child["token"], indent=2))
        print("\n[DETAIL] Filesystem checks:")
        print(json.dumps({"worker": worker["filesystem"], "child": child["filesystem"]}, indent=2))
        print("\n=== SUMMARY ===")
        print(f"{sum(checks.values())}/{len(checks)} checks passed")
        print("NOTE: This PoC does not test or enforce network isolation, executable allowlisting, or a complete sandbox.")
        print(f"Evidence retained at: {root}")
        return 0 if all(checks.values()) else 1
    except Exception as exc:
        print(f"[ERROR] {type(exc).__name__}: {exc}")
        traceback.print_exc()
        print(f"Evidence directory retained for inspection: {root}")
        return 1


def parse_args():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("worker", "child"))
    parser.add_argument("--protected-file")
    parser.add_argument("--allowed-file")
    parser.add_argument("--report")
    parser.add_argument("--child-report")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.role:
        raise SystemExit(worker_main(args))
    raise SystemExit(controller_main())
