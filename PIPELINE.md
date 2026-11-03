# Feature pipeline configuration

- feature_root: docs/features
- completed_root: docs/features-completed
- branch_policy: feature-branch
- delivery_cadence: end
- test_cmd: python dev/steamos_test.py && python tools/sync_shared.py --check && xvfb-run -a python dev/steamos_gui_test.py && python tools/build_steamos.py --native && xvfb-run -a dist/BL4FixSetup-SteamOS --smoke-test
- test_scope_hint: For installer logic run `python dev/steamos_test.py`; for the setup window run `python dev/steamos_gui_test.py` on a desktop or `xvfb-run -a python dev/steamos_gui_test.py` on Linux; for shared package copies run `python tools/sync_shared.py --check`. Select additional focused tests for the changed code.
- seam_domains: Steam launch options and Proton/SDK loading; installer game-file, save, settings and backup operations; mod packaging and shared UI link; direct-connect networking and firewall; update signing and release assets; cross-platform Windows and SteamOS compatibility.
- deploy.check: none
- push_effect: A push triggers the SteamOS package workflow, including Linux tests and an uploaded build artifact. Publishing a release triggers release verification. Pushing source does not itself publish a release.

The test command is the SteamOS installer matrix from `.github/workflows/steamos.yml`.
It requires Linux, Python 3.11, Tk, Xvfb, PyInstaller 6.11.1 and network access.
Changes outside that scope also require the relevant existing Windows, in-game,
release or hardware checks. A GitHub-hosted run is separate evidence and does not
establish Steam Deck gameplay.
