# P2-TREE-01 — Process Tree Containment PoC

Standalone Windows PoC. Requires Windows, Python 3.10+, and PyWin32.

Run from this directory:

```powershell
python .\p2_tree_01.py
```

Scenarios:
- A: Worker + Child are observed in the same Job; exact member count and PPID chain checked.
- B: Worker + Child + Grandchild are observed in the same Job; exact member count and PPID chain checked.
- C: `TerminateJobObject` termination is verified through retained process handles, exit codes, and Job active-process count.
- D: A breakaway request is expected to be denied by the Job configuration. This does not prove that a process can never escape every enclosing Job.

The controller uses `QueryInformationJobObject(..., JobObjectBasicProcessIdList)` as a PID sequence, matching the PyWin32 API contract. Other Job information classes used for limits/accounting return dictionaries.

Scenario D keeps an unexpectedly successful breakaway child suspended until it is assigned to a private `KILL_ON_JOB_CLOSE` guardian Job. If guardian assignment fails, the worker explicitly terminates the child. No controller Named Pipe handoff is used.

Important: a successful run on the target Windows host is required before declaring P2-TREE-01 complete. This PoC is not a complete sandbox or a proof of filesystem/network isolation.