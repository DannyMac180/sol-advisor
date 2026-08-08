# Changelog

All notable changes to Sol Advisor are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and Semantic Versioning.

## [Unreleased]

### Added

- Cursor local-clone installation guide plus developer smoke-test procedure with guarded setup, evidence, and cleanup steps.
- Guarded macOS TypeScript installer for Cursor's project-scoped local MCP compatibility bridge, including workspace-isolated data, receipt validation, concurrent-edit refusal, crash recovery, and lifecycle tests.

### Fixed

- Windows now validates `${PLUGIN_DATA}` and backup privacy from owner and ACL SIDs instead of Bun's POSIX mode projection, while retaining POSIX mode checks on Linux and macOS.
- Cursor 3.15.6 local installation now uses a verified directory copy instead of an externally resolved symlink.
- Replaced the ineffective GUI `PATH` relaunch workaround with a project-native MCP bridge after live testing showed Cursor's plugin MCP process cannot resolve the canonical bare `bun` command.
- Documented Cursor 3.15.6's independent Customize workspace selector, repeated source-consent boundary, and full-process restart fallback when a window reload leaves the shared MCP process disconnected.

## [0.5.0] - 2026-08-07

### Added

- Canonical Agent Plugins v1 manifest alongside the Codex adapter manifest.
- Lazy parent-chat setup interview and fail-closed setup gate.
- Cross-client configuration and native adapters for Codex, Cursor, VS Code/Copilot, and Kiro.
- Bun stdio MCP server with safe preview, consent, install, validation, reset, and uninstall tools.
- Durable, private configuration state and transactional managed-file recovery.
- Pinned plugin/MCP schemas, CI, tag parity, flattened release gates, and comprehensive security/runtime tests.
- Explicit user-visible Luna / Max app-task lane with parent-owned review and acceptance.

### Changed

- The orchestrator now inherits the parent chat's selected model and effort.
- Routine, high-complexity, and advisor roles use exact user-selected native IDs.
- Retained native Codex delivery on Terra / High with a fresh Sol / High review.
- Retired the Luna native companion role while preserving exact legacy migration.

[Unreleased]: https://github.com/DannyMac180/sol-advisor/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/DannyMac180/sol-advisor/releases/tag/v0.5.0
