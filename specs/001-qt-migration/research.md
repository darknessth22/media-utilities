# Research: PyQt6 GUI Migration

## Testing Framework

- **Decision**: Use standard library `unittest` for backend testing, and manual acceptance testing for the GUI.
- **Rationale**: The project currently relies on ad-hoc scripts (`test_conv.py`, `test_executable.py`) without a formal testing framework. To align with Constitution Principle V (Simplicity & YAGNI) and minimize new dependencies, `unittest` will be used for any automated regression tests, while the `PySide6` UI will be verified manually against the User Scenarios defined in `spec.md`.
- **Alternatives considered**: `pytest` (rejected to avoid introducing a new third-party dependency just for the migration phase).
