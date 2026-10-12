# MARK LV project analysis

Reviewed on 9 October 2026. Scope: this local project snapshot, its architecture, setup, action dispatch, persistence, remote dashboard, automation, documentation, and selected isolated behavior checks.

**Assessment:** A substantial desktop assistant prototype with useful separation of tools, audio, UI, and memory. It has reproducible data-loss bugs and security boundary failures that should be fixed before relying on autonomous computer control or remote access. Passing syntax and SDK schema checks does not establish that its voice session or every advertised capability works.

## Project at a glance

| Item | Observation |
| --- | --- |
| Python source | 49 files, 25,776 lines, including comments and blank lines |
| Largest files | `ui.py`: 5,849 lines; `main.py`: 2,322; `actions/browser_control.py`: 1,132 |
| Discoverable actions | 17 files declare `TOOL`; all 17 declarations pass the installed Gemini SDK's `FunctionDeclaration` validation |
| Inline session tools | 8 declarations in `main.py` |
| Plugins in this snapshot | Loader, package initializer, and template; no active community plugin files |
| Local Python | 3.14.7; README lists 3.11–3.13 and setup warns about newer versions |
| Installed key dependencies | google-genai 2.29.0, PyQt6 6.11.0, numpy 2.5.2, sounddevice 0.5.6, fastapi 0.141.1, playwright 1.63.0, cryptography 49.0.0 |
| Quality infrastructure | No test files, CI workflows, `pyproject.toml`, or dependency lockfile found |
| Version-control context | This directory has no Git repository metadata; history and whether credentials were ever committed cannot be assessed |

`setup.py` is an installation script, not a Python packaging definition. It installs `requirements.txt` and Playwright browsers into the selected interpreter. The license text and README identify the project as CC BY-NC 4.0 with personal/non-commercial terms.

## How the application works

1. `main.py` creates the PyQt UI on the main thread and starts a daemon thread containing the asyncio application loop.
2. `JarvisLive` discovers built-in tools from `actions/*.py`, then community tools from `plugins/*.py`. It builds a Gemini Live configuration from prompt text, identity, memory, and tool declarations.
3. Microphone input is mono PCM at 16 kHz. Sounddevice callbacks schedule audio onto the asyncio queue. Wake-word, mute, speaking/echo, and push-to-talk state govern local input delivery.
4. Gemini returns audio, transcriptions, session-resumption updates, and function calls. Playback is 24 kHz. Audio and transcript-derived visemes animate the software-rendered head.
5. Inline tools operate on session state. Discovered tools execute in worker threads, receiving UI/speech context through signature introspection.
6. `memory/long_term.json` stores facts and session summaries. A selected memory block enters the system prompt; additional facts can be retrieved locally.
7. The dashboard supplies HTTP/WebSocket commands, phone audio, uploads, and transcript updates. It starts automatically from the application loop.

| Area | Main files | Responsibilities |
| --- | --- | --- |
| Application orchestration | `main.py` | Session setup/reconnect, audio pipelines, tool execution, wake/sleep, background activity |
| Desktop interface | `ui.py` | HUD, overlays, customization, device selection, video/camera, memory, confirmations |
| AI access | `core/gemini.py`, `core/prompt.txt` | One-shot model ladders, cooldowns, Live fallback, assistant instructions |
| Local safeguards | `core/confirm.py`, `core/undo.py` | UI-mediated irreversible actions and in-process undo records |
| Audio and avatar | `core/audio_devices.py`, `core/wake_word.py`, `core/hotkey.py`, `core/echo.py`, `core/viseme.py`, `core/avatar*.py` | Device probes, local detection, input handling, facial rendering |
| Computer actions | `actions/` | Browser, files, settings, messaging, code generation, search, reminders, media |
| Persistence | `memory/` | Configuration, personal facts, summaries, search |
| Phone dashboard | `dashboard/server.py`, `dashboard/static/` | Pairing, commands, sockets, upload/download, remote UI |
| Extensions | `core/action_loader.py`, `core/plugin_loader.py`, `plugins/_template.py` | Discovery, declaration validation, routing, plugin settings |

## What is already well designed

- Deterministic tool discovery, collision detection, and per-file failure handling keep a broken extension from rejecting the entire registry.
- The confirmation service fails closed without a UI and gives the human a real button; a model-supplied `confirmed=yes` is not the authorization mechanism for guarded power/network actions.
- Memory storage and prompt size are separate. Local recall avoids sending the entire store every session.
- There are explicit session-resumption handles, reconnect paths, device fallback, bounded microphone queues, and cooldowns for several model failure classes.
- File deletion uses the OS trash when available, while video resolution has a cancellation sequence and starts playback muted.
- The avatar uses existing numpy/PyQt dependencies and includes an actual face mesh. Optional camera, video, and wake-word paths are separated from the core rendering.

These are useful foundations. They do not eliminate the concrete issues below.

## Priority findings

### 1. High — credential ignore rules do not work

**Evidence:** `.gitignore:8–13`. Several patterns have comments appended on the same line. Git treats that trailing text as part of the pattern; comments belong on lines beginning with `#`. This follows the [official Git pattern rules](https://git-scm.com/docs/gitignore).

**Reproduced:** In a disposable Git repository containing an exact copy of this `.gitignore`, `config/api_keys.json`, `config/certs/jarvis.key`, a WhatsApp session path, an OAuth token path, and a client-secret path were **not ignored**. The separate `memory/long_term.json` rule and Python-cache rules worked.

**Impact:** Creating a repository and staging this directory can include credentials and TLS private keys despite the README's assurances.

**Fix:** Put explanatory comments on separate lines and check all sensitive paths with `git check-ignore`. If anything is already tracked, ignoring it will not remove it from history. Assess exposure before deciding whether rotation is necessary.

The local config contains a nonempty API-key value, but it does not match the standard Google API-key shape used in the check. Its validity was not tested. A valid matching TLS certificate/private-key pair is present, dated 8 October 2026. Local presence alone is not evidence that either credential was publicly shipped or leaked.

### 2. High — copying over an existing file destroys its recoverability

**Evidence:** `actions/file_controller.py:328`. `shutil.copy2` overwrites an existing destination; undo subsequently deletes the destination without retaining its previous contents.

**Reproduced:** Copying `source.txt` over a destination containing different data replaced it. Calling undo removed the destination entirely.

**Fix:** Reject collisions by default or preserve the destination's original bytes and metadata in a bounded backup before overwriting. Undo must restore the prior destination.

### 3. High — rename bypasses the permitted-path boundary

**Evidence:** `actions/file_controller.py:371`. The source is checked, but `target.parent / new_name` is not. Absolute paths replace the parent; traversal components can escape it.

**Reproduced:** With `_SAFE_ROOTS` restricted to a disposable directory, renaming a file to an absolute path in a different directory succeeded.

**Fix:** Require `new_name` to be a single filename and validate the resolved destination before mutation. Recheck destinations after directory/symlink resolution in other operations too.

### 4. High — application launching exposes a shell-injection path

**Evidence:** `actions/open_app.py:80`. The Windows URI branch builds `start {app_name}` with `shell=True` from tool-provided text.

**Reproduced safely:** With `Popen` mocked, the input `custom: & echo AUDIT_ONLY` reached it as `start custom: & echo AUDIT_ONLY` with shell execution enabled. No command was actually executed.

**Impact:** A tool intended to launch an application can instead carry additional shell operations, bypassing action-specific safeguards.

**Fix:** Launch resolved executables with argument lists and `shell=False`; use an appropriate Windows API for validated URI protocols. Restrict accepted protocols and avoid raw command strings.

### 5. High — generated projects have no effective execution boundary

**Evidence:** `actions/dev_agent.py:158`, `:242`, `:298`. Model-returned file paths are joined directly to the project directory; dependency names are passed to pip in the current interpreter; the model-selected command is run as an executable/argument list.

**Inspection finding:** Absolute or traversal paths can escape the project directory. Generated code runs with the user's normal filesystem/network privileges. Dependency installation changes the assistant's own environment. The command uses split arguments, not a general shell, but it can still choose powerful executables and arguments.

**Fix:** Validate every resolved path, reject option-like or unexpected dependency specifications, use a separate environment per project, and execute through a constrained runner with explicit user-visible authority. Restrict code-running actions and bound runtime/output. Apply the same execution policy to `code_helper`.

### 6. High — revoking paired devices leaves access tokens active

**Evidence:** `dashboard/server.py:659`. Revocation clears `_device_sessions` but not `_tokens`, `_token_keys`, encryption caches, or connected WebSockets. Tokens have no per-token expiration check.

**Reproduced:** An in-process ASGI request revoked one paired device, then its existing bearer token still submitted a command successfully with HTTP 200. An unauthenticated command correctly returned 401.

**Fix:** Associate access tokens and sockets with devices; revoke both current and future access, close affected sockets, remove cached secrets, and expire sessions. Recheck authorization for long-lived sockets rather than only at connection time.

### 7. High — dashboard startup can expand network access without an explicit remote-enable step

**Evidence:** `main.py:2082`, `dashboard/server.py:99`, `:856`. Dashboard startup is automatic. Servers bind all interfaces. The Windows helper can ask for elevation to add port/program firewall rules and change public network profiles to private.

**Inspection finding:** This happens when the assistant starts, before the user clicks the remote-control UI. The OS elevation prompt still requires approval; the concern is the scope and timing of the requested network changes.

**Fix:** Default remote access to disabled, start it on an explicit user action, bind only the intended interface, scope rules to the intended network, and avoid changing every public network profile. Report startup failures visibly.

### 8. High — messaging uses unverified keystrokes and can claim success incorrectly

**Evidence:** `actions/send_message.py:137`. The generic desktop path uses fixed sleeps, searches, pastes, and presses Enter, then reports that the message was sent without reading the selected recipient or delivery state.

**Inspection finding:** WhatsApp attempts a verified helper, but `plugins/_whatsapp_core.py` is absent from this snapshot, so the blind fallback applies. Other generic desktop transports also use it.

**Fix:** Read and verify the active window, recipient/conversation, draft, and send result. Report an attempt rather than delivery until verified. Treat sending as an explicitly authorized operation in the shared action policy.

### 9. Medium — concurrent memory updates lose data; writes are not atomic

**Evidence:** `memory/memory_manager.py:57`, `:118`, `:159`. Load and save lock individually, leaving the read-modify-write transaction unprotected. `forget` and session summaries follow similar patterns. Configuration writes also perform unguarded read-modify-write operations.

**Reproduced:** Two synchronized fact updates retained only one of the two facts.

**Fix:** Lock the full transaction and write to a temporary file followed by atomic replacement. Validate loaded schemas and retain a recovery copy. Centralize config updates under the same policy rather than repeating them across modules.

### 10. Medium — undo can erase changes made after the assistant's operation

**Evidence:** `actions/file_controller.py:34`, `:53`, `:229`. Undo for a created file deletes whatever currently occupies that path. Undo for a write restores old text without checking whether the user subsequently edited it. Reading backups with `errors="ignore"` also loses binary or invalid UTF-8 bytes.

**Reproduced:** A file created by the assistant, then edited independently, was deleted by undo.

**Fix:** Store byte-exact backups plus the expected post-operation state/hash. Refuse or request a conflict decision if the file has changed. Preserve newer data in directory-copy undo as well. Track undo failures honestly rather than always prefixing results with “Undone.”

### 11. Medium — long tools stall reception and are not cancelled with speech

**Evidence:** `main.py:1472`, especially the function-call loop around `:1586`; `interrupt` at `:922`.

**Inspection finding:** The receiving coroutine awaits each tool before reading further Live messages. Executor use keeps the asyncio loop available, but the receive task itself remains occupied. Local interrupt clears playback; it does not cancel arbitrary tool work. The receive path does not explicitly handle server interruption or tool-call cancellation events.

**Fix:** Keep reception continuously draining, track running tool jobs by call ID, handle server cancellation/interruption, and prevent results from stale sessions from being sent. Add cooperative cancellation and deadlines; cancelling a Python future alone does not stop its worker thread.

### 12. Medium — Live model options and one-shot limits need capability-aware handling

**Evidence:** `core/gemini.py:371`, `:420`; `main.py:1065`, `:1119`. FAST/SMART ladders now lead with a throwaway Live session, unlike the README's measured REST ordering. The Live path transfers only the system instruction from generation config, dropping caller settings such as response format/schema and output limits.

The worker-thread join can finish before the worker's connection-plus-generation timeout. Its semaphore is released regardless of whether the worker is still running, so it is not a strict bound on active one-shot sessions. Also, when every rung is cooling down, `call()` retries the full ladder.

Google's current [Live capability guide](https://ai.google.dev/gemini-api/docs/live-api/capabilities) labels 3.1 Flash Live as a legacy preview and documents that it lacks asynchronous function calling and proactive audio. That makes model-aware declarations/configuration important. This review did not test which aliases the configured key can access.

**Fix:** Use capabilities per model, keep structured generation on a path that enforces its schema, enforce a whole-request deadline, release concurrency slots when workers actually exit, and respect all-rungs cooldown. Evaluate model upgrades with integration checks rather than changing names blindly.

### 13. Medium — dashboard encryption and resource controls are incomplete

**Evidence:** `dashboard/server.py:76`, `:81`, `:569`, and command/upload/socket handlers. Pairing has no login-attempt limiter; command queues and token collections have no global bounds. Each upload can be 500 MB, with no overall storage budget. Failed TLS generation can leave HTTP serving enabled.

The six-character pairing key has about 30 bits of possible values and is hashed into the AES key. CBC commands have no MAC and plaintext commands are also accepted. Uploads, login responses, and transcript broadcasts do not use that command encryption. AES key size does not establish equivalent session-key strength or complete dashboard protection. The [cryptography documentation](https://cryptography.io/en/latest/hazmat/primitives/symmetric-encryption/) explains why encryption alone does not authenticate messages.

**Fix:** Require TLS for remote control, throttle pairing attempts, bound commands/messages/uploads/storage, expire tokens, and rely on a consistent transport/security design. If separate payload encryption remains necessary, use authenticated encryption and a high-entropy session secret.

### 14. Medium — a game-install path disables the global automation failsafe

**Evidence:** `actions/game_updater.py:353` assigns `pyautogui.FAILSAFE = False` without restoring it.

**Impact:** Using this action changes the shared module state for later automation, removing the emergency mouse-corner stop enabled by other tools.

**Fix:** Preserve and restore state in `try/finally`, or keep the failsafe enabled. Add a shared cancellation control across automation actions.

### 15. Medium — plugin import advice contradicts the documented supply-chain fix

**Evidence:** `core/plugin_loader.py:195`. `_load_error` still recommends pip installation for missing project packages other than `plugins`.

**Reproduced:** A missing `core.future_helper` produced `pip install core`, exactly the advice the README says was removed.

**Fix:** Identify first-party roots such as `core`, `actions`, `config`, `dashboard`, and `memory`, and advise an app/plugin compatibility update. For third-party imports, use declared distribution mappings rather than assuming an import name is the pip package name.

## Documentation, maintainability, and secondary issues

- The README says 12 bundled actions; this tree declares 17, including `flight_finder`, `game_updater`, `code_helper`, `dev_agent`, and `youtube_video`.
- The README's local-data description is incomplete. Memory enters Gemini's prompt, and file contents, images, screenshots, and session-summary text can be sent for AI processing. Voice is not the only outgoing data.
- The model-ladder description and several comments reflect different versions of the code. The template/plugin structure is useful, but the distribution snapshot and release claims need a consistency pass.
- `core/llm_client.py`, `core/stt.py`, `core/tts.py`, and `core/installer.py` have no import references anywhere in this Python tree. They do not provide an active offline/Ollama path for this Gemini Live application. Remove, archive, or deliberately integrate them with tests.
- `main.py` and `ui.py` together account for 8,171 lines, about 32% of Python source. Split session lifecycle, audio, tool jobs, and dashboard integration from orchestration; split UI panels and media/device controllers from the main window.
- Tool schemas guide the model, but dispatch does not centrally validate incoming arguments or enforce a common permissions policy. Safeguards vary across file tools, generated code, browser actions, and external messaging. Plugins execute ordinary Python at import time and run with the process's privileges; they are trusted extensions, not isolated skills.
- `setup.py` uses a relative `requirements.txt` path even though it computes `HERE`; invoking it from a different working directory can select the wrong file or fail. Use `HERE / "requirements.txt"`.
- Broad version ranges and unbounded packages make fresh installations differ over time. Use a tested lock/constraints set with deliberate updates for rapidly changing tools such as yt-dlp, and separate core dependencies from unused community extras.
- Several subprocess/media paths report success without checking return codes. Long file-processing operations may run for many minutes. Bound operation duration/output and return a structured status instead of inferring success from strings.
- The file processor accepts arbitrary readable paths and archive destinations, unlike the file controller's home-directory boundary. Use one shared file policy, extraction size/member limits, and output collision handling.
- `main.py` globally patches `subprocess.Popen` on Windows. That affects dependencies as well as project tools and discards `startupinfo`. Prefer a local subprocess wrapper.
- Conversation history and playback queues can grow during long sessions. Bound local storage/queues independently of Gemini context compression.
- Qt wrappers use signals for many operations, which is good; any remaining cross-thread widget reads or state changes need a targeted thread-ownership audit.

## Checks performed and limits

| Check | Result |
| --- | --- |
| Parse every Python source with `ast.parse` | 49/49 passed |
| Locate principal installed dependencies | Available; versions recorded above |
| Validate action declaration dictionaries with installed Gemini SDK | 17/17 passed |
| Test exact ignore rules in disposable repository | Five credential/session paths not ignored; memory/cache controls ignored |
| Isolated file-controller operations | Confirmed overwrite/undo loss, rename escape, and deletion of later edits |
| Synchronized concurrent fact writes | One of two facts lost |
| Mocked Windows application launch | Confirmed raw shell-metacharacter forwarding; no shell operation executed |
| First-party plugin import failure | Confirmed incorrect `pip install core` advice |
| In-process dashboard HTTP requests | Confirmed active-token survival after revocation and 401 for unauthenticated command |
| Parse local certificate and private key | Matching, parseable pair; values suppressed |
| Inventory tests/build/CI and alternative-module references | No tests/CI/lockfile; no imports of the four alternative backend modules |

Functional checks used temporary data or mocked boundaries. Dashboard class methods were loaded from its AST into an isolated test context, avoiding its module-level upload-folder creation, network-IP probes, firewall helper, and real server startup.

The GUI was not launched. No microphone/camera recordings, desktop interaction, real messaging, generated-code execution, package installation, firewall changes, or authenticated Gemini calls were performed. Consequently voice latency, model access, browser profile compatibility, wake-word accuracy, rendering, and Windows/macOS/Linux behavior remain integration-test work. No application source was changed by this analysis; this report is the deliverable.

## Recommended implementation order

1. Fix credential ignore patterns and review distribution contents. Fix file overwrite/undo and rename validation. Remove raw shell launch paths.
2. Make remote access explicit, repair revocation/expiration, require TLS, and bound pairing/queues/uploads.
3. Introduce a shared action policy for file access, generated-code execution, messaging, and extension trust. Restore automation failsafes.
4. Make memory/config transactions atomic. Make undo conflict-aware and byte-exact.
5. Keep Live reception independent of tool execution; add cancellation, per-model capabilities, and strict request/concurrency limits.
6. Add focused regression tests for the reproduced cases, then integration checks for audio, reconnection, and browser behavior on supported Python/OS combinations.
7. Reconcile the README with the shipped tree, isolate unused backends, split oversized modules, and establish reproducible installs.

The most valuable next work is resolving the reproduced safety and data-integrity defects. Additional features should follow those fixes and a small, meaningful regression suite.
