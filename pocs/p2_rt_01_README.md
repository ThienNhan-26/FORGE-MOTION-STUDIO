# P2-RT-01 — Restricted Token PoC

Standalone Windows security PoC. Requires Windows, Python 3.10+, and PyWin32.

Run from this directory:

```powershell
python .\p2_rt_01.py
```

The controller creates two disposable files and applies explicit DACLs only to those files:

- `protected_interactive_only.txt`: grants read access through the INTERACTIVE group (SID `S-1-5-4`).
- `workspace_user_sid.txt`: grants read access through the current user's SID.

It creates a restricted primary token using `CreateRestrictedToken` with:
- `DISABLE_MAX_PRIVILEGE`, reducing enabled privileges.
- INTERACTIVE in `SidsToDisable`, which should become deny-only in the new token.

The controller launches the worker with `CreateProcessAsUser`. The worker inspects its token and attempts both file reads, then launches a child using ordinary `CreateProcess`. The child repeats the token and file checks to verify that the restricted token is inherited.

Expected evidence:
- The unrestricted controller can read both files.
- Worker and child show the INTERACTIVE SID with `SE_GROUP_USE_FOR_DENY_ONLY`.
- Worker and child cannot read the INTERACTIVE-only file but can read the user-SID workspace file.
- Enabled privileges are reduced to `SeChangeNotifyPrivilege` or fewer, depending on the host.
- Worker and child exit successfully.

API nuance: `IsTokenRestricted` reports whether the token has a restricting-SID list. This PoC tests SID disabling and privilege reduction, not a `SidsToRestrict` list; therefore `IsTokenRestricted` may correctly return `False`. The deny-only group attribute and actual access-denied result are the evidence for this test.

If `CreateProcessAsUser` fails due to caller privileges or token constraints, the PoC fails closed and reports the Windows error. It never elevates privileges, retries with an unrestricted token, changes system ACLs, or modifies files outside its disposable temporary directory.

The temporary evidence directory is printed and retained for inspection.

Limitations: this PoC does not test or enforce network isolation, executable allowlisting, Job Object limits, or complete sandbox containment. Restricted Tokens alone do not provide those controls. It does not alter Phase 1 or FORGE Core.
