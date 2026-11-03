# SteamOS launch reliability

**Status:** approved — in execution · owner approved 2026-11-03
**Review:** 2026-11-03 GO — independent reviewer gpt-6-astra/high; 0/1/2 findings; 3 edits applied; open 0/0/0; coverage complete (F1, F2, F3 resolved).
**Home:** steamos-launch-reliability · none

## Outcome and boundaries

Make the native SteamOS installer explain why installed files do not establish that the Python SDK loaded, check the SDK installation meaningfully, and compose BL4 Fix's launch requirements with a user's existing Steam launch options without losing their lsfg-vk setup. The owner reports installed mods absent in game, with existing Decky lsfg-vk options. Exact launch text, Proton version, game path and current SDK logs are **unverified**; loader/runtime, wrong directory and mod/UI failures remain hypotheses.

The implementation produces read-only diagnostics, an explicit paste/preview/copy workflow and troubleshooting instructions. It does not edit Steam configuration, execute pasted commands, install runtimes, switch Proton, replace Decky settings, delete a prefix, manipulate saves, upgrade the pinned SDK, or promise hardware compatibility. No generic shell parser, automatic log upload or new dependency. Keep Windows installers and in-game mod behavior unchanged.

Owner-selected authoring root: `D:/Projects/BL4-Fix-Deck`; common directory `.git` there; branch `steamos-launch-reliability`, no dedicated worktree. Verified using `git rev-parse --show-toplevel --path-format=absolute --git-common-dir`, `git branch --show-current`, `git worktree list --porcelain`, `git status --short`. Location authority does not grant publication/build authority.

## Verified code map — verified at 99cd9b9

| Anchor | Existing behavior / reuse |
|---|---|
| `installer/steamos.py:23-46` | Game ID/executable, fixed `LAUNCH_OPTIONS`, native/Flatpak/library discovery. Reuse selected game validation; users must compare with Steam's Browse Local Files. |
| `installer/steamos.py:85-127` | `safe_target`, `game_folder`, `read_record`, `installed_mods`; reuse path checks and record reading. Record `mods` still needs validation before diagnostic use. |
| `installer/steamos.py:130-180`, `:223-292` | Backups, rollback, payload selection and SDK-file classification. No mutation changes are needed for this feature. |
| `installer/steamos.py:335-345` | `health(game, archive) -> list[str]` checks only loader/config/UI link and catalog mods already present. Missing expected mods and other SDK dependencies can escape this report. Preserve its return shape. |
| `installer/steamos.py:374-412` | CLI `--check` joins health messages; install prints fixed launch text; argument parsing currently precedes game selection. A print-only composition mode must branch before game discovery/root checks and never fall through to install. |
| `installer/steamos_gui.py:164-186`, `:298-346` | System page, install completion, health worker and copy callback. Replace fixed copy with explicit input/preview/copy, reuse existing task/error plumbing. |
| `dev/steamos_test.py:31-49`, `:70-195` | Synthetic payload and preservation/rollback tests. Fixture currently lacks most SDK members; enrich diagnostic fixtures without network or real games. |
| `dev/steamos_gui_test.py:21-39`, `:54-63`, `:102-105` | GUI fixture, apply assertion and fixed clipboard assertion must evolve with the workflow. |
| `installer/build.py:52-71`, `tools/manual_zip.py:162-181` | SDK v0.3 SHA-256 pin and manual archive aggregation. Do not change pin or packaging format. |
| `tools/build_steamos.py:23-40`, `:45-64` | Source zip explicitly includes `steamos.py` and GUI; frozen executable imports them. Keeping backend helper in `steamos.py` avoids a new packaging dependency. |
| `docs/STEAMOS.md:41-53`, `:110-129`, `README.md:70-80` | Current copy/merge instructions and troubleshooting; all user-facing copies must agree. |
| `.github/workflows/steamos.yml:3-9`, `:19-39`, `PIPELINE.md` | Every push runs Linux tests/build/artifact upload; published releases run extra verification. Linux smoke is not physical Deck acceptance. |

Producer/consumer grep performed: `rg -n -F -e 'LAUNCH_OPTIONS' -e 'steamos.health' -e 'health(games' -e 'copy_options' -e 'WINEDLLOVERRIDES' -e 'pf_tricks' -e 'lsfg' installer dev tools docs README.md`. Producers/consumers are the backend constant/CLI, GUI preview/copy/health, GUI clipboard test, and SteamOS docs. No launch composer or lsfg integration exists in those sources. Packaging consumers checked separately with `rg -n 'steamos|setup.py|PyInstaller' tools/build_steamos.py`.

Pinned archive evidence: read-only SHA-256/member listing of `installer/build/cache/oak2-sdk-v0.3.zip` matched the `installer/build.py:53` pin. It includes the loader, Unreal/Python DLLs, Python 3.14 runtime and SDK bootstrap/mod dependencies named in LR-101. The cache is evidence, not a committed dependency. Reproduce with Python `hashlib.sha256(Path(...).read_bytes())` and `zipfile.ZipFile(...).namelist()` before changing SDK assumptions; health never downloads.

Do not touch: saves/profile data, `sdk_mods/settings`, Steam `localconfig.vdf`, compatdata, Decky files, existing launch options on disk, SDK pin, signing/releases, Windows installer/core, shared package copies, in-game mods, install/uninstall transaction behavior or backups. Diagnostic fixtures may contain sentinel versions of protected files, never real user data.

## Decisions and contracts

1. **Installation versus activation.** Keep `health(game, archive) -> list[str]` read-only. Report selected root, expected-file comparison, loose-folder shadowing and a separate explicit “SDK runtime activation not checked” result. Never label missing logs as proof of failure or old logs as current success. Runtime proof comes from the user's fresh game launch and SDK console, followed by the BL4 Fix F7 menu. Installed-file counts and an F7 failure alone cannot diagnose the loader.
2. **Launch text is data.** Add pure `compose_launch_options(existing: str) -> str` in `steamos.py`, raising `ValueError` for ambiguity. Support only literal leading assignments, optional literal wrapper/arguments, one unquoted standalone `%command%`, and literal game arguments. Retain unrelated original spans, quotes, spacing and tilde expansion. Never execute or expand input, edit VDF, or round-trip through `shlex.join`. LR-102 defines all supported/refused cases.
3. **Minimum edits.** Add/normalize `BL4FIX_STEAMOS=1`, merge only `dsound=n,b` into the single leading Wine override, retain/append exactly one `-pf_tricks=vcrun2022`. Preserve other DLL entries and arguments; repeat composition is byte-identical. A lone BL4 flag value `0` changes visibly to `1`; conflicting/duplicate owned settings, grouped dsound entries and other runtime tricks require manual reconciliation.
4. **Bounded fallback.** Empty input yields the existing default. Reject complex shell syntax, expansion, control characters, ambiguous placeholders, `env` wrappers and misplaced owned assignments. Literal quoted override semicolons are allowed. Preserve original input and clipboard on refusal; give manual-merge guidance. Preserved wrapper text does not prove it forwards environment. No claim of arbitrary shell support.
5. **User-owned workflow.** System page accepts complete pasted current options, shows preview and validates again when copying. Empty input means an empty Steam field. No persistence/logging or execution of launch text. CLI gets print-only `--launch-options EXISTING`, before discovery/root checks, mutually exclusive with operational options. Installation output distinguishes files installed from launch setup and labels the fixed default for empty fields only. LR-103 defines UI/CLI acceptance.
6. **Troubleshooting evidence.** Ask for the full current launch text, chosen Proton version, Steam Browse Local Files path and whether double-tilde opens the SDK console before concluding a cause. Instructions preserve a copy of original launch text before manual edits. First check files/root, then composition/runtime guidance, then SDK console and BL4 Fix UI separately. Any temporary test without lsfg is an explicit user-performed A/B test with restoration instructions, never an automatic removal. Do not request saves or complete logs; use only relevant redacted error excerpts if further diagnosis requires them.

External primary references checked 2026-11-03: [SDK installation](https://bl-sdk.github.io/oak2-mod-db/) specifies the dsound override/runtime argument and double-tilde console/`mods` verification; [SDK FAQ](https://bl-sdk.github.io/oak2-mod-db/faq/#can-i-use-this-on-steam-decklinuxmac) warns Proton results vary and covers `vcrun2022`. These support guidance, not proof for this user's device. The [Decky plugin fork README](https://github.com/jbragado/decky-lossless-scaling-vk) documents an `LSFG_PROCESS=decky-lsfg-vk %command%` form and the [experimental plugin README](https://github.com/PacificSilent/decky-lsfg-vk-experimental/blob/main/README.md) describes the public `~/lsfg %command%` form. Treat them as example fixtures, not identification of the installed plugin/version.

### Verification

Owner/repo resolution: focused row coverage, then one settled final Linux `test_cmd`; no conflict and no per-row full matrix. There is one cumulative feature candidate (LR-101 through LR-104), no independently delivered row increments. Each dispatch records phase, focused/full scope, commands, exact candidate/tree and boundary. Focused receipts cover changed contracts; independent integration GO and an exact-tree final PASS are required before delivery. Documentation/status-only successors may reference an unchanged tested executable tree only with an inspected diff. No paper-planning execution tests are required.

Final Linux command, with all legs required and native exits captured:

```sh
python dev/steamos_test.py && python tools/sync_shared.py --check && xvfb-run -a python dev/steamos_gui_test.py && python tools/build_steamos.py --native && xvfb-run -a dist/BL4FixSetup-SteamOS --smoke-test
```

Prerequisites: Linux, Python 3.11, Tk, Xvfb, PyInstaller 6.11.1 and build download access (`PIPELINE.md`). No Windows-only/local synthetic result substitutes for Linux qualification. Inspect packaged source and frozen smoke after the shared helper/UI changes. Actual Deck/gameplay/lsfg acceptance remains G-H; lack of hardware is reported, never converted to PASS.

### Delivery

| Field | Decision |
|---|---|
| Cadence | `end`, from `PIPELINE.md`; one final source candidate, because backend/UI/docs jointly provide the usable workflow. |
| Candidate | Final independently accepted LR-101–LR-104 candidate, bound to exact SHA/tree at G-T. Audience: SteamOS installer users. |
| Action scope and targets | Current task: local reviewed planning documents only. Proposed future G-P planning/configuration publication: repository `Farkoal2128/bl4-fix-deck`, remote `origin` (`https://github.com/Farkoal2128/bl4-fix-deck.git`), target `main`; export only the allowlist, never merge the authoring branch. Implementation integration/push to `main`, optional feature-branch push, release/tag/version and device installation/activation: unresolved, require later explicit scope. Application deployment/consumer migration: none. |
| Predicates and workflow | G-P requires independent GO covering the plan and exact configuration blob plus explicit owner approval of this disclosed planning/configuration scope; freshly fetched target, isolated allowlisted export, exact diff/ancestry verification and coordinator delivery workflow. If target `PIPELINE.md` has the same blob, leave it unchanged; if absent, export the approved blob; if different, reconcile and independently review the proposed configuration before publication and obtain owner approval for changed scope. Implementation delivery additionally requires G-T and an explicit owner decision about G-H evidence; never infer release authority. |
| Owner authority | The request authorizes writing/reviewing this new plan and convergence, not approving/publishing it or running implementation. A later explicit approval of this disclosed plan can authorize local implementation and G-P publication of the reviewed planning documents plus the exact `PIPELINE.md` blob below only. It grants no implementation publication or authoring-branch merge; a no-push/local-only instruction overrides that proposal. G-D remains unresolved. |
| Planning/configuration allowlist/effects | Only `docs/features/steamos-launch-reliability/PLAN.md`, `tickets/LR-101.md`, `tickets/LR-102.md`, `tickets/LR-103.md` beneath the same folder, plus root `PIPELINE.md` from commit `99cd9b9`, exact blob `6d9797a0e7ee30a1c3ebc4c89cb84886bc00c28f`. Read-only `git ls-tree origin/main -- PIPELINE.md` showed it absent in the cached target; refresh at G-P. `git rev-parse 99cd9b9:PIPELINE.md` verifies the approved blob. This configuration makes the published plan usable with its declared repository facts. A push triggers `.github/workflows/steamos.yml` tests/build/artifact upload, but no release publication. No other branch contents are authorized by G-P. |

## Steps

| Step | Ticket(s) | Kind | Tier | Effort | Status |
|---|---|---|---|---|---|
| 🚦 G-P | G-P | owner approval / planning-config publication | seam | small | ✅ approved 2026-11-03; planning/configuration only published to origin/main at a012dcbc096fc83bc6f1eb5998099933da920c0e; remote verified; no implementation or release publication |
| 1 | LR-101 | read-only SDK diagnostics | seam | medium | pending |
| 2 | LR-102 | launch composition | seam | medium | pending |
| 3 | LR-103 | GUI and CLI workflow | seam | medium | pending |
| 4 | LR-104 | user instructions | seam | small | pending |
| 🚦 G-T | G-T | final technical checkpoint | seam | medium | pending |
| 🚦 G-H | G-H | physical Deck acceptance | seam | medium | pending |
| 🚦 G-D | G-D | implementation delivery decision | seam | small | pending |

### G-P — owner decision, coordinator execution

Scope: future explicit local implementation approval and separately disclosed planning/configuration publication above, including only the pinned `PIPELINE.md` blob. Predicate: independent zero-significant-findings review covering that configuration, structural preflight and exact approved allowlist/destination. Export in isolation; never merge the authoring branch or publish implementation through this gate. Apply the same/absent/different target-configuration rules in Delivery. Current authority is paper-only; stop here after review. Owner may instead choose local-only implementation, making publication inapplicable. Review GO is not owner approval; never set `approved — in execution` without that approval.

### LR-101 — [SDK diagnostics](tickets/LR-101.md)

### LR-102 — [Launch composition](tickets/LR-102.md)

### LR-103 — [GUI and CLI workflow](tickets/LR-103.md)

### LR-104 — instructions (after LR-101–LR-103)

- Goal/files: update `docs/STEAMOS.md` and the SteamOS section of `README.md` for actual new controls and print-only CLI.
- Accept: both docs distinguish file presence, SDK console and BL4 Fix F7; cover empty input, both evidenced lsfg examples, preserved non-dsound overrides, unsupported/manual fallback and original-text restoration.
- Accept: no claim of Deck success; explain Proton/runtime uncertainty without deleting prefix/saves, changing Decky or installing a runtime automatically.
- Verify: compare examples to actual helper output and grep all fixed-copy instructions using the code-map command; `git diff --check -- README.md docs/STEAMOS.md`. No repeated full suite for docs.
- Stop if: example syntax is unsupported, verified upstream guidance conflicts, or changes would require extra production files. Final boundary is G-T.

### G-T — coordinator technical decision

Scope: settled final candidate only. Predicates: all row contracts and focused receipts, independent integration GO, full Linux command above with zero exits, packaged source inspection and frozen smoke, no unaccounted dirty paths. Record exact tested commit/tree and environment. Missing Linux access is a named qualification hold. Coordinator authority after implementation approval covers these routine checks; this gate authorizes no push or physical installation.

### G-H — owner hardware evidence/decision

Scope: user-performed acceptance on the actual Deck. Obtain the exact original launch text and Proton/plugin versions, then preserve the original text, compare Steam's game path, inspect diagnostics, apply reviewed composed options manually and launch. Evidence: fresh SDK console opens without relevant Proton/SDK errors; `mods` works; F7 shows BL4 Fix and one harmless visible mod behavior; existing lsfg remains active; original launch text can be restored. User reports observations and relevant redacted errors. No save/prefix/Decky mutation or automatic runtime install. Hardware success is a separate receipt with device/build/options context, never inferred from G-T. Owner may explicitly defer hardware validation for source-only delivery at G-D; device success stays unverified and must be disclosed.

### G-D — owner delivery decision

Scope/authority unresolved. Present accepted candidate, G-T receipts, G-H result or explicit deferral, exact desired branch/remote, and any release/version/installation proposal before requesting those effects. Coordinator follows only the subsequently approved scope and existing delivery workflow; source push is not release publication. All preparation is local until that decision.
