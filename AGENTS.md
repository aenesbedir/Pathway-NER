# Agent rules

## Ask before running anything on TRUBA/ARF

Never run a command against TRUBA/ARF — SSH, rsync, scp, or by reusing an
already-open control-socket/ControlMaster session — without naming the exact
command to the user first and getting an explicit yes.

This covers read-only commands (`ls`, `cat`, `squeue`, `sacct`, `whoami`,
directory listings) exactly as much as state-changing ones (`sbatch`, file
transfers, `authorized_keys` edits, key generation). An active VPN tunnel or
an already-authenticated SSH session does not by itself authorize reusing it
— ask every time, not just before the first command in a session.

TRUBA/ARF here means anything reachable through the interface hosts
(`arf-ui1`, `arf-ui4`, `arf-ui5`, or whichever `172.16.6.x` host is in use),
`/arf/home`, `/arf/scratch`, and the `slurm/*.slurm` job scripts once
submitted.

Why: TRUBA is a shared, quota-limited account (job history, disk quota,
account-suspension risk for hammering login nodes) — see
`docs.truba.gov.tr/5-sikca_sorulan_sorular`. Unlike ordinary local read-only
checks, a command here has a cost and a footprint the user should see before
it runs.
