# TradePulse Global Agent Rules

## Documentation and Architecture Policies

- **Post-Bug Fix Documentation Rule:** After resolving any bug where a README change is required, you must always generate or update detailed architecture documentation.
- The documentation must be comprehensive and detail exactly how the **Master**, **Slave**, and **Redis** interact in various edge cases.
- It must explicitly cover:
  1. Detailed operational scenarios (success, failure, disconnects).
  2. Retry logic and idempotency handling.
  3. SL/TP detection and synchronization logic.
  4. The 60-second database sync architecture.
- Ensure that the bug fix journal (`docs/bug_fix_journal.md`) is also kept up to date with the latest resolutions.
