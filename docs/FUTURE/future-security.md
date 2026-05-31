# Future: Directory Security
**Status:** planned

## On initialisation

`perag init` sets permissions on `.perag/` and informs the user with a warning on
stderr in all cases. The warning includes a sentence clarifying that it does not affect
the operation of the program, and closes with the standard advisory to seek further
guidance.

**Unix (macOS and Linux):**

`perag init` sets `.perag/` to `700` (owner read/write/execute only) and prints:

> Warning: `.perag/` permissions set to 700 (owner-only). This does not cover extended
> ACLs — if your system uses ACL-based access control, those are not managed by perag.
> This warning does not affect the operation of the program and is provided as a
> security advisory only. For more information on what this means for your specific
> setup, ask your AI assistant, or other trusted digital companion.

**Windows:**

`perag init` does not attempt to set any permissions and prints:

> Warning: Running on Windows — perag has not set any access permissions on `.perag/`.
> Ensure that only your user account has access to this directory. This warning does
> not affect the operation of the program and is provided as a security advisory only.
> For more information on what this means for your specific setup, ask your AI
> assistant, or other trusted digital companion.

## On subsequent operations

On Unix, perag checks `stat().st_mode` on `.perag/` at startup and emits a warning to
stderr and the log if the directory is more permissive than `700`. The operation
proceeds regardless — the check is advisory only.

No equivalent runtime check is performed on Windows.

## ACLs

macOS and Linux support extended ACLs that can grant access beyond what Unix permission
bits express. perag does not read or set ACLs on any platform. The warning message
acknowledges this explicitly. Users who require ACL-level control should verify their
setup independently — or ask their AI assistant, or other trusted digital companion.

## Why not now

- Permission hardening is straightforward on Unix but unimplementable without
  `pywin32` on Windows, which is too heavy a dependency for this tool's audience.

Revisit when the user base includes environments where shared machines or multi-user
setups make directory permissions a real concern.
