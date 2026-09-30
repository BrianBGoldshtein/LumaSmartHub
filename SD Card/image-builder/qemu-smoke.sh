#!/usr/bin/env bash
# Diagnostic only: QEMU lacks the Pi bootloader and several real peripherals.
# Never use this copied DTB or overlay as a shipping image or hardware boot proof.
set -euo pipefail
IMAGE_DIR=$(realpath "${1:?Path to completed image-luma-pi4 directory}")
[[ -f "${IMAGE_DIR}/luma-pi4.img" && -f "${IMAGE_DIR}/boot.vfat" ]] || exit 1
[[ ${2:-} == '' || ${2:-} == --api-check || ${2:-} == --gateway-check || ${2:-} == --tailscale-check || ${2:-} == --backup-check || ${2:-} == --pi-connect-check || ${2:-} == --pi-connect-preflight ]] || { echo 'Optional second argument: --api-check, --gateway-check, --tailscale-check, --backup-check, --pi-connect-check or --pi-connect-preflight' >&2; exit 1; }
[[ $# -le 3 && ( ${3:-} == '' || ${3:-} == --diagnostics || ${3:-} == --diagnostics-unconfined || ${3:-} == --diagnostics-stack ) ]] || { echo 'Optional third argument: --diagnostics, --diagnostics-unconfined or --diagnostics-stack (fresh, unprovisioned images only)' >&2; exit 1; }
SMOKE_SECONDS=180
KERNEL_ARGS='console=ttyAMA1,115200 root=/dev/disk/by-slot/system fsck.repair=yes rootwait systemd.show_status=yes'
if [[ ${2:-} == --api-check || ${2:-} == --gateway-check || ${2:-} == --tailscale-check || ${2:-} == --backup-check || ${2:-} == --pi-connect-check || ${2:-} == --pi-connect-preflight ]]; then
  # systemd.run normally replaces default.target. Keep the appliance's graphical
  # boot and add the generated diagnostic unit alongside it, only in this VM.
  # Output is health/version/database only; never dump settings or credentials.
  KERNEL_ARGS+=' systemd.unit=graphical.target systemd.wants=kernel-command-line.service systemd.run_success_action=none systemd.run_failure_action=none'
  if [[ ${2:-} == --gateway-check || ${2:-} == --tailscale-check ]]; then
    # Start the otherwise-disabled unit only in this disposable VM. No token,
    # state mutation, or host network forwarding: an empty POST must get 401.
    KERNEL_ARGS+=' systemd.wants=luma-shortcut-gateway.service'
    KERNEL_ARGS+=' systemd.run="/usr/bin/curl --fail --silent --show-error --retry 60 --retry-connrefused --retry-delay 2 --max-time 2 http://127.0.0.1:8742/api/v1/health --next --silent --show-error --retry 60 --retry-connrefused --retry-delay 2 --max-time 2 --request POST http://127.0.0.1:8743/command"'
    if [[ ${2:-} == --tailscale-check ]]; then
      # Disposable offline VM only: start daemon without up/login, exercising
      # its real firewall, TUN and local broker; do not read/generated identities.
      KERNEL_ARGS=${KERNEL_ARGS%\"}
      KERNEL_ARGS+=' --next --silent --show-error --retry 60 --retry-connrefused --retry-delay 2 --max-time 30 --header Content-Type:application/json --data-binary @/opt/luma/qualification/tailscale-status.json http://127.0.0.1:8742/api/v1/tailscale"'
      KERNEL_ARGS+=' systemd.wants=luma-tailscaled.service'
    fi
  elif [[ ${2:-} == --backup-check ]]; then
    # Exercise actual socket activation and Linux SO_PEERCRED on the image.
    # No removable device is attached; the authorized luma client must get an
    # empty inventory from the root-owned broker over the packaged socket.
    KERNEL_ARGS+=' systemd.wants=luma-backup.socket'
    if [[ ${3:-} == --diagnostics-stack ]]; then
      # Disposable VM only: register SIGUSR1 with faulthandler and export the
      # temporary sitecustomize path before the activated broker starts.
      KERNEL_ARGS+=' systemd.run="/usr/bin/python3 -c exec(bytes([105,109,112,111,114,116,32,111,115,59,112,61,39,47,114,117,110,47,108,117,109,97,45,100,101,98,117,103,39,59,111,115,46,109,97,107,101,100,105,114,115,40,112,44,101,120,105,115,116,95,111,107,61,84,114,117,101,41,59,111,112,101,110,40,112,43,39,47,115,105,116,101,99,117,115,116,111,109,105,122,101,46,112,121,39,44,39,119,39,41,46,119,114,105,116,101,40,39,105,109,112,111,114,116,32,102,97,117,108,116,104,97,110,100,108,101,114,44,115,105,103,110,97,108,59,102,97,117,108,116,104,97,110,100,108,101,114,46,114,101,103,105,115,116,101,114,40,115,105,103,110,97,108,46,83,73,71,85,83,82,49,44,97,108,108,95,116,104,114,101,97,100,115,61,84,114,117,101,41,39,41]))"'
      KERNEL_ARGS+=' systemd.run="/usr/bin/systemctl set-environment PYTHONPATH=/run/luma-debug"'
    fi
    if [[ ${3:-} == --diagnostics-unconfined ]]; then
      # A VM-only differential probe: clear only SystemCallFilter in /run on
      # the qcow2 overlay to identify whether that sandbox prevents accept().
      KERNEL_ARGS+=' systemd.run="/usr/bin/python3 -c exec(bytes([105,109,112,111,114,116,32,111,115,59,112,61,39,47,114,117,110,47,115,121,115,116,101,109,100,47,115,121,115,116,101,109,47,108,117,109,97,45,98,97,99,107,117,112,46,115,101,114,118,105,99,101,46,100,39,59,111,115,46,109,97,107,101,100,105,114,115,40,112,44,101,120,105,115,116,95,111,107,61,84,114,117,101,41,59,111,112,101,110,40,112,43,39,47,111,118,101,114,114,105,100,101,46,99,111,110,102,39,44,39,119,39,41,46,119,114,105,116,101,40,39,91,83,101,114,118,105,99,101,93,92,110,83,121,115,116,101,109,67,97,108,108,70,105,108,116,101,114,61,92,110,39,41]))"'
      KERNEL_ARGS+=' systemd.run="/usr/bin/systemctl daemon-reload"'
    fi
    KERNEL_ARGS+=' systemd.run="-/usr/sbin/runuser -u luma -- /opt/luma/venv/bin/python -c s=__import__(bytes([115,111,99,107,101,116]).decode()).socket(1,1);s.settimeout(60);s.connect(bytes([47,114,117,110,47,108,117,109,97,45,98,97,99,107,117,112,46,115,111,99,107]).decode());s.sendall(bytes([123,34,97,99,116,105,111,110,34,58,34,108,105,115,116,34,125,10]));print(s.makefile(bytes([114,98]).decode()).readline().decode().strip())"'
    if [[ ${3:-} == --diagnostics-stack ]]; then
      KERNEL_ARGS+=' systemd.run="/usr/bin/systemctl kill --signal=SIGUSR1 luma-backup.service"'
      KERNEL_ARGS+=' systemd.run="/usr/bin/journalctl -u luma-backup.service -n 40 --no-pager"'
    fi
  elif [[ ${2:-} == --pi-connect-preflight ]]; then
    # Diagnostic only, in the disposable qcow2 VM: exercise the exact packaged
    # CLI and dedicated user's bus. Never sign in or export an account URL.
    KERNEL_ARGS+=' systemd.wants=luma-pi-connect-setup.socket'
    KERNEL_ARGS+=' systemd.run="/usr/bin/systemctl start user@1001.service"'
    KERNEL_ARGS+=' systemd.run="/usr/bin/echo LUMA-PI-CONNECT-PREFLIGHT-ON"'
    KERNEL_ARGS+=' systemd.run="-/usr/sbin/runuser -u luma-admin -- /usr/bin/env HOME=/home/luma-admin USER=luma-admin LOGNAME=luma-admin XDG_RUNTIME_DIR=/run/user/1001 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus /usr/bin/rpi-connect on"'
    KERNEL_ARGS+=' systemd.run="/usr/bin/sleep 5"'
    KERNEL_ARGS+=' systemd.run="/usr/bin/echo LUMA-PI-CONNECT-PREFLIGHT-VNC-OFF"'
    KERNEL_ARGS+=' systemd.run="-/usr/sbin/runuser -u luma-admin -- /usr/bin/env HOME=/home/luma-admin USER=luma-admin LOGNAME=luma-admin XDG_RUNTIME_DIR=/run/user/1001 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus /usr/bin/rpi-connect vnc off"'
    KERNEL_ARGS+=' systemd.run="/usr/bin/echo LUMA-PI-CONNECT-PREFLIGHT-SHELL-OFF"'
    KERNEL_ARGS+=' systemd.run="-/usr/sbin/runuser -u luma-admin -- /usr/bin/env HOME=/home/luma-admin USER=luma-admin LOGNAME=luma-admin XDG_RUNTIME_DIR=/run/user/1001 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus /usr/bin/rpi-connect shell off"'
  elif [[ ${2:-} == --pi-connect-check ]]; then
    # Fresh image only: ask the actual local setup broker for status as its
    # authorized API user. The broker runs `rpi-connect status`; this does not
    # sign in, enable remote shell, or reveal a verification URL.
    KERNEL_ARGS+=' systemd.wants=luma-pi-connect-setup.socket'
    KERNEL_ARGS+=' systemd.run="/usr/bin/curl --fail --silent --show-error --retry 60 --retry-connrefused --retry-delay 2 --max-time 2 http://127.0.0.1:8742/api/v1/health"'
    KERNEL_ARGS+=' systemd.run="-/usr/sbin/runuser -u luma -- /opt/luma/venv/bin/python -c exec(bytes([105,109,112,111,114,116,32,97,115,121,110,99,105,111,59,102,114,111,109,32,108,117,109,97,46,112,105,95,99,111,110,110,101,99,116,95,115,101,116,117,112,32,105,109,112,111,114,116,32,112,105,95,99,111,110,110,101,99,116,95,114,101,113,117,101,115,116,59,32,114,61,97,115,121,110,99,105,111,46,114,117,110,40,112,105,95,99,111,110,110,101,99,116,95,114,101,113,117,101,115,116,40,123,34,97,99,116,105,111,110,34,58,34,115,116,97,116,117,115,34,125,41,41,59,32,112,114,105,110,116,40,34,112,105,45,99,111,110,110,101,99,116,45,115,101,116,117,112,45,114,101,115,112,111,110,115,101,34,44,114,46,103,101,116,40,34,97,118,97,105,108,97,98,108,101,34,41,44,114,46,103,101,116,40,34,115,105,103,110,101,100,95,105,110,34,41,44,114,46,103,101,116,40,34,115,116,97,116,101,34,41,41]))"'
    if [[ ${3:-} == --diagnostics ]]; then
      # Repeated systemd.run= commands are later ExecStart lines in the same
      # oneshot; '-' lets these read-only diagnostics run after a probe timeout.
      KERNEL_ARGS+=' systemd.run="/usr/bin/systemctl show luma-backup.service -p ActiveState -p SubState -p MainPID -p CPUUsageNSec -p TasksCurrent -p ControlGroup"'
      KERNEL_ARGS+=' systemd.run="/usr/bin/journalctl -u luma-backup.service -n 25 --no-pager"'
      KERNEL_ARGS+=' systemd.run="/usr/bin/systemctl show luma-backup.service -p MainPID -p CPUUsageNSec -p TasksCurrent -p ControlGroup"'
      KERNEL_ARGS+=' systemd.run="/usr/bin/cat /sys/fs/cgroup/system.slice/luma-backup.service/cpu.stat"'
      KERNEL_ARGS+=' systemd.run="/usr/bin/sleep 5"'
      KERNEL_ARGS+=' systemd.run="/usr/bin/cat /sys/fs/cgroup/system.slice/luma-backup.service/cpu.stat"'
      KERNEL_ARGS+=' systemd.run="/usr/bin/ss -xlpn"'
    elif [[ ${3:-} == --diagnostics-unconfined ]]; then
      KERNEL_ARGS+=' systemd.run="/usr/bin/systemctl show luma-backup.service -p ActiveState -p SubState -p MainPID -p CPUUsageNSec"'
      KERNEL_ARGS+=' systemd.run="/usr/bin/journalctl -u luma-backup.service -n 25 --no-pager"'
    fi
  else
    KERNEL_ARGS+=' systemd.run="/usr/bin/curl --fail --silent --show-error --retry 60 --retry-connrefused --retry-delay 2 --max-time 2 http://127.0.0.1:8742/api/v1/health"'
  fi
fi
if [[ ${3:-} == --diagnostics || ${3:-} == --diagnostics-unconfined || ${3:-} == --diagnostics-stack ]]; then
  # Keep the failed normal run. This longer diagnostic is not a normal-boot
  # timing pass; console journal output is only appropriate for fresh images.
  SMOKE_SECONDS=360
  KERNEL_ARGS+=' systemd.journald.forward_to_console=1'
  KERNEL_ARGS=${KERNEL_ARGS//--retry 60/--retry 150}
fi
SMOKE_ROOT=$(mktemp -d /tmp/luma-qemu.XXXXXXXX)
for asset in kernel8.img initramfs8 bcm2711-rpi-4-b.dtb; do
  mcopy -i "${IMAGE_DIR}/boot.vfat" "::${asset}" "${SMOKE_ROOT}/${asset}"
done
# QEMU attaches the SD image to mmcnr, unlike the physical Pi's emmc2 path.
# Model firmware metadata only in this disposable copy, so official slot rules
# can resolve the root device without changing the image's cmdline or fstab.
fdtput -t s "${SMOKE_ROOT}/bcm2711-rpi-4-b.dtb" /aliases mmc0 /soc/mmcnr@7e300000
fdtput -t s "${SMOKE_ROOT}/bcm2711-rpi-4-b.dtb" /aliases mmc1 /emmc2bus/mmc@7e340000
fdtput -c "${SMOKE_ROOT}/bcm2711-rpi-4-b.dtb" /chosen/bootloader
fdtput -t u "${SMOKE_ROOT}/bcm2711-rpi-4-b.dtb" /chosen/bootloader boot-mode 1
fdtput -t u "${SMOKE_ROOT}/bcm2711-rpi-4-b.dtb" /chosen/bootloader partition 1
qemu-img create -f qcow2 -F raw -b "${IMAGE_DIR}/luma-pi4.img" "${SMOKE_ROOT}/overlay.qcow2" 16G
printf 'Diagnostic directory: %s\n' "${SMOKE_ROOT}"
printf 'Bounded emulator duration: %s seconds; diagnostic journal: %s\n' "${SMOKE_SECONDS}" "${3:-off}"
set +e
timeout --signal=TERM "${SMOKE_SECONDS}" qemu-system-aarch64 -M raspi4b -m 2G -smp 4 \
  -kernel "${SMOKE_ROOT}/kernel8.img" -initrd "${SMOKE_ROOT}/initramfs8" \
  -dtb "${SMOKE_ROOT}/bcm2711-rpi-4-b.dtb" \
  -drive "file=${SMOKE_ROOT}/overlay.qcow2,if=sd,format=qcow2" \
  -append "${KERNEL_ARGS}" \
  -display none -serial "file:${SMOKE_ROOT}/serial.log" -monitor none -nic none -no-reboot
QEMU_STATUS=$?
set -e
printf 'Emulator status: %s; inspect %s/serial.log (timeout is not a boot-pass assertion)\n' "${QEMU_STATUS}" "${SMOKE_ROOT}"
if [[ ${2:-} == --api-check || ${2:-} == --gateway-check || ${2:-} == --tailscale-check || ${2:-} == --pi-connect-check ]]; then
  if grep -Fq '"status":"ok","database":"ok"' "${SMOKE_ROOT}/serial.log"; then
    echo 'API health and database integrity responded in emulation; hardware remains unqualified.'
  else
    echo 'No successful API health response captured.' >&2
    exit 1
  fi
fi
if [[ ${2:-} == --pi-connect-check ]]; then
  if grep -Fq 'pi-connect-setup-response True False ' "${SMOKE_ROOT}/serial.log"; then
    echo 'Packaged Pi Connect setup socket returned fresh-device status to the authorized Luma user; no account was enrolled.'
  else
    echo 'No authorized Pi Connect setup-broker status response captured; inspect the fresh VM log.' >&2
    exit 1
  fi
fi
if [[ ${2:-} == --backup-check ]]; then
  if grep -Fq '{"volumes":[]}' "${SMOKE_ROOT}/serial.log"; then
    echo 'Packaged backup socket activated the root broker; the installed luma UID passed peer authorization and received an empty offline USB inventory.'
  else
    echo 'No authorized backup-broker inventory response captured; inspect the fresh VM log.' >&2
    exit 1
  fi
fi
if [[ ${2:-} == --gateway-check || ${2:-} == --tailscale-check ]]; then
  if grep -Fq '{"detail":"Command authentication required."}' "${SMOKE_ROOT}/serial.log"; then
    echo 'Dormant gateway started in the disposable VM and rejected the unauthenticated command.'
  else
    echo 'No gateway authentication rejection captured; inspect its startup log.' >&2
    exit 1
  fi
fi
if [[ ${2:-} == --tailscale-check ]]; then
  if grep -Fq '"state":"NeedsLogin","command_url":null' "${SMOKE_ROOT}/serial.log"; then
    echo 'Offline Tailscale daemon/firewall and UID-checked setup broker responded; no account enrolled.'
  else
    echo 'No successful offline Tailscale setup response; inspect the fresh VM log.' >&2
    exit 1
  fi
fi
