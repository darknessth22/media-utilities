# Phase 1: Data Model

## Existing Entities

The `UserSettings` entity (`core/settings.py`) already exists to persist `.theme_mode`. 
No core data models need modification for this UI-only feature. The `theme_mode` defaults to `auto` and can be toggled to `light` or `dark`.

## UI State

When the theme is toggled, `SettingsManager.save(self.settings)` is called, and `root.theme_manager.set_mode(mode)` applies it. The GUI needs to maintain the current state of the icon representing the theme (Sun vs Moon).

*No new database, storage files, or entities are required.*
