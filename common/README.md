# Common Utilities

### Purpose

This directory contains utility modules that are **shared across multiple, distinct projects in our organization**.

Its primary role is to avoid code duplication and provide a single source of truth for organization-wide utilities that are not part of any library.

### Guiding Principles

Code should be placed in this directory only if it meets the following criteria:

1.  **Shared:** It must be used by multiple top-level directories (e.g., imported by both `src/` and `test_scripts/`). If a utility is only used within the core library, it belongs in `src/utils.py`.
2.  **Generic:** The utility should be general-purpose and not tied to the specifics of any library. For example, a logging configuration is generic; a packet-building function is not.
