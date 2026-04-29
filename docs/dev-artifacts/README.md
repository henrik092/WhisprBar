# Development Artifacts

This folder keeps reference-only files that are useful for future design or manual QA,
but are not part of the runtime application.

## UI Prototypes

Archived from the temporary Flow parity worktree on 2026-04-29:

- `ui-prototypes/flow-ux-options.html`
- `ui-prototypes/flow-ux-a-refined.html`
- `ui-prototypes/flow-ux-a2-light.html`
- `ui-prototypes/settings-ux-options.html`
- `ui-prototypes/settings-ux-b-refined.html`

These files are static preview mockups. They are kept only as design references for
future Flow overlay and settings UI work. The application does not import or execute
them.

## Cleanup Policy

Generated test output such as `.pytest_cache/`, `htmlcov/`, `.coverage`, `__pycache__/`,
and Nextcloud `conflicted copy` files should be deleted instead of archived.
