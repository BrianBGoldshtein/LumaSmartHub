# USB infrared implementation — transport foundation

2026-09-28. Source/software tests only. No real remote recording, appliance command, account enrollment, purchase or physical test has occurred. Exact Woozoo models and USB adapter remain undecided; see HARDWARE_ADDITIONS.md. The transport is connected to the durable two-fan store, owner-local API and themed FanSetup flow; production scene dispatch/trigger/API/UI integration is also implemented; see ROOM_DEVICES.md and SCENES.md. A disposable real HTTP/WebSocket fan API check now covers synthetic discovery→learn→test→observe, independent scene eligibility, uncertain receipts, busy/no-queue and cancellation. Existing images are unchanged and outdated. Older integration checklists below describe the transport checkpoint, not a reason to recreate the fan workflow.

## Transport boundary

`ir_broker.py` provides a local Unix socket client and socket-activated broker. The dedicated unprivileged `luma-ir` account is distinct from the API/desktop `luma` account. Socket mode0660/root:luma plus Linux SO_PEERCRED admit only the actual luma UID. No network listener or arbitrary command/path input. Setup/privacy/permission and learned-command semantics MUST be enforced by the application before calling this transport; socket authorization is not a substitute for those checks.

Three exact operations: discover; learn one device with optional documented carrier; send one validated frame through one adapter/emitter. Strict single-line JSON rejects duplicates, extra fields, nonfinite numbers, invalid Unicode/control text and oversize messages. Sixteen device results and16384wire bytes maximum. IDs are opaque USB metadata hashes, never caller paths. Raw signals are internal data, not remote Shortcut/voice parameters.

The broker permits one operation globally, no queue, a half-second cooldown after completion/cancellation and at most eight admitted connections. It reads requests within3seconds, bounds socket responses and revokes the operation on client disconnect or extra pipelined input. Already-buffered pipelining is rejected before dispatch. Later disconnect can race a completed transmission; the caller must preserve an unknown receipt, never retry.

Workers run the fixed installed `python -I -m luma.ir_linux` command, input via stdin, no shell, no caller argv/environment, no stderr logs. Isolated Python ignores user site/PYTHONPATH; final image must keep interpreter/module root-owned. Child deadlines: discover4seconds, learn12seconds (capture itself10), send4seconds; spawn3seconds; reap2seconds. Cancel/timeout kills/reaps the child. Cancellation during spawn retains the spawning task and kills a late-created child. If a killed child cannot be reaped promptly, or cancellation interrupts cleanup, this broker fails closed until administrator restart. Service KillMode=control-group bounds ordinary shutdown; a genuinely uninterruptible kernel driver remains an administrator/hardware fault, not a claim that Python can stop every syscall.

Client uses one request, never retries; malformed/lost replies after possible send become unknown. A successful driver write returns `sent_unconfirmed`, NEVER a claimed appliance state. The application must durably claim a command before dispatch, recheck owner/configuration around awaits, record unknown on cancellation and never replay it after restart.

## Linux adapter

`ir_linux.py` targets the Linux generic ioctl ABI used by ARM64 and x86_64. It enumerates only USB-backed `/sys/class/lirc/lircN`, requires real character nodes and matching sysfs major/minor, opens with NOFOLLOW/NONBLOCK/CLOEXEC, and probes capabilities. GPIO is not a candidate. Transmit requires raw-pulse sending AND carrier selection; receive requires MODE2. Ambiguous duplicate identities are dropped. Internal paths, serial strings and device internals do not appear in public discovery.

Identity includes physical USB port, vendor/product, optional serial, interface and features. Before use, node type/rdev, features and USB identity are checked again. This detects observed replacement, not an impossible guarantee against every USB hotplug race. A physically identical no-serial replacement in the same port cannot be distinguished by this metadata. Device routing/independence proof must be invalidated when configuration or observed capabilities change; no-serial adapters require explicit owner review. Moving ports changes the ID. Discovery does not prove fan compatibility.

Learning saves/restores receive mode, temporarily enables carrier measurement when supported and requests timeout reports. It drains already-buffered data with a strict eight-read bound, then captures at most10seconds/16384bytes. Real long space or timeout data ends a frame; userspace silence does NOT make a truncated recording valid. Missing delimiter, overflow, malformed alternation or an unknown carrier fails. Hardware without appropriate framing/carrier capability may require another adapter or documented carrier input; none is guessed automatically.

`ir_signal.py` bounds carrier to20–60kHz, odd pulse-first/pulse-last duration lists7–511edges, individual intervals below20ms and total250ms. These limits reject common short repeat fragments and excessive recordings. They do NOT decode/validate every remote protocol, identify a button's meaning, handle every toggle-bit protocol or establish safe automation semantics. Actual repeated-press and separate on/off tests are required after owner hardware authorization. Unsupported protocols must be shown as unsupported, not made up or blindly replayed.

Send validates capabilities and exactly one emitter if selectable. A nonzero transmitter-mask ioctl result is rejected before writing. There is exactly one `os.write`, no resend after partial writes/errors. Carrier20–60kHz is not a promise that all physical adapters support that entire range. Hardware rejection is handled without falling back to another adapter/channel or guessed frequency.

## Source packaging

- `luma-ir` entry point, `luma-ir.socket` enabled at image installation; no IR service is started by installer and no client is wired yet. Socket activation alone does not scan or emit IR.
- `luma-ir.service`: dedicated locked/no-home account, zero capabilities/no-new-privileges, read-only system/home/data exclusions, AF_UNIX only, syscall/resource bounds, whole-process-group termination. It needs real USB device nodes, so PrivateDevices is intentionally false; access is controlled by DAC and worker USB checks. This is not a claim of a cgroup per-device allowlist.
- `72-luma-ir.rules`: only USB-backed LIRC nodes become0660/root:luma-ir; removes uaccess after70-uaccess and before73-seat-late. API/desktop is NOT added to luma-ir. Final image must verify actual rule ordering and permissions on device insertion; pre-existing ACLs on an already-running upgraded host are not qualified by source syntax checks.
- Shortcut gateway additionally masks `/run/luma-ir.sock`; no direct remote hardware bypass. Final image exact-file inventory includes both units and the rule.

## Evidence

- Windows full backend suite:750passed,8Linux-only skipped,77.63seconds; existing Starlette/httpx deprecation warning.65new cross-platform IR tests included.
- Debian WSL qualification venv:73IR tests passed (the65 plus5synthetic sysfs/installed-worker and3real Unix-socket tests),4.51seconds. No physical devices accessed. Sysfs/device metadata and ioctl/write/read behavior are simulated; real sockets exercise kernel peer credentials and connection cancellation. Installed isolated worker receives an invalid action and rejects it before any discovery.
- Linux package installed into the existing disposable qualification venv with `pip install --no-deps .`; wheel SHA25696fde81ca09104cf124890acdd8e53d43789353931e7c329c383360a75c4a38a. This is not the final dependency-qualified ARM image. Later package edits require reinstallation before installed-worker tests.
- `image-builder/test_ir_service.py`:4Linux checks passed, including native systemd/udev/bash syntax validation. Temporary unit copy substitutes the unavailable image-only ExecStart with the existing qualification interpreter solely for executable-existence validation. No service started, user created, udev event triggered or device touched. Static gateway packaging4tests also passed.
- Tests cover signal/byte limits; no delimiter/no carrier/changed carrier/truncation/overflow; drain/mode restoration; USB-only identity/node/capability/duplicate rejection; one write and mask rejection; strict IPC/output sanitization; fixed child invocation; deadlines/cancel/late spawn/unreapable child; busy/cooldown; peer denial/disconnect/pipelining; no retry or false confirmed state.
- `tests/fan_preview.py` + `tests/fan_live_check.py` exercise the production fan API/store/runtime over real localhost HTTP/WebSocket against a deterministic fake transport and temporary SQLite. PASS: two-emitter routing, repeated absolute-state observations, independent scene eligibility, no waveform exposure, durable unknown after transport failure, request-busy/no-queue and bounded cancellation. Focused `tests/test_fans.py`:30 passed in Debian. These checks do not execute the Unix broker, USB, udev or systemd sandbox and do not establish a physical fan protocol.

Not yet evidence: enforcement under the production systemd sandbox, actual udev ACLs, real USB driver ioctl behavior, actual Pi ARM64 runtime, chosen fan protocol, power state, repeated button acceptance, emitter independence or physical latency. Preserve these as explicit later gates.

## Next feature9 implementation

1. Two durable named fan slots, selected adapter/emitter, revision/generation, validated learned buttons and command semantics. No default buttons or automatic power assumptions. Corrupt state fails closed; same-card saves persist, portable restore unlinks/disables. Separate local owner-only bounded learn/cancel/test flows and pre-dispatch durable unknown receipts; one-hour per-device manual overrides.
2. Guided independent reception tests in BOTH directions, tied to exact routing/button configuration. Owner hardware authorization required. Toggle/unknown commands need manual confirmation and are ineligible for autonomous scenes. Expose absence/incompatibility honestly. Do not pretend preliminary USB hardware recommendations are finalized.
3. Four empty/disabled scenes Morning/Night/Arrive/Away. Explicit trigger opt-in; distinguish calendar/manual morning/night. Authenticated-phone arrival30seconds/departure3minutes; cooldown5minutes; boot/PIN/Tailscale/token refresh are not arrivals. Claims before I/O, partial/unknown receipts, no missed-run replay, one-hour per-device override.
4. Themed Room devices setup and final review using existing TouchField/dirty/busy/defer/privacy patterns; local voice and explicitly allowlisted remote appliance commands (never raw IR/learning/credentials). Reuse existing purifier controls and preserve its freshness/configuration guards. Complete remaining purifier UI checks in ROOM_DEVICES.md.
5. Feature10 encrypted settings-only USB, all-theme/live HTTP/WS qualification, NEW immutable ARM image and final physical wiring/SD-flash/first-boot/network/SSH guide. Hardware tests remain deferred by owner. Game state and frozen Tetris untouched.

## Primary interface references

- [Linux LIRC userspace interface](https://docs.kernel.org/userspace-api/media/rc/lirc-dev.html)
- [Linux UAPI constants](https://github.com/torvalds/linux/blob/master/include/uapi/linux/lirc.h)
- [Read/packet contract](https://docs.kernel.org/userspace-api/media/rc/lirc-read.html)
- [Write contract](https://docs.kernel.org/userspace-api/media/rc/lirc-write.html)
- [Carrier measurement](https://docs.kernel.org/userspace-api/media/rc/lirc-set-measure-carrier-mode.html)
- [Receiver timeout](https://docs.kernel.org/userspace-api/media/rc/lirc-set-rec-timeout.html)
- [Transmitter mask](https://docs.kernel.org/userspace-api/media/rc/lirc-set-transmitter-mask.html)

Kernel headers/documentation were reviewed; installed Debian native validators and udev rule order were inspected. Hardware-independent software evidence does not certify an actual adapter, installation or appliance.
