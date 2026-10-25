#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this installer as root." >&2
  exit 1
fi

SOURCE_ROOT=${1:-/opt/luma-source}
APP_VERSION=$(sed -n 's/^version = "\([^"]*\)"$/\1/p' "${SOURCE_ROOT}/backend/pyproject.toml" | head -n 1)
if [[ ! ${APP_VERSION} =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
  echo "Invalid application release version." >&2
  exit 1
fi
RELEASES_ROOT=/opt/luma-releases
INSTALL_ROOT=${RELEASES_ROOT}/${APP_VERSION}
if [[ -e /opt/luma || -L /opt/luma || -e ${INSTALL_ROOT} ]]; then
  echo "Refusing to replace an existing Luma release or application path." >&2
  exit 1
fi
install -d -m 0755 -o root -g root "${RELEASES_ROOT}" "${INSTALL_ROOT}"
install -d -m 0755 -o root -g root /etc/luma
install -m 0644 -o root -g root "${SOURCE_ROOT}/system/luma-update-ed25519.pub" /etc/luma/luma-update-ed25519.pub

apt-get update
apt-get install -y --no-install-recommends \
  bluetooth bluez chromium curl labwc wvkbd fonts-dejavu-core pipewire pipewire-audio \
  libpipewire-0.3-modules libspa-0.2-modules \
  pipewire-pulse python3 python3-venv wlr-randr ddcutil dbus-user-session \
  lightdm avahi-daemon i2c-tools pulseaudio-utils gcc python3-dev linux-libc-dev espeak-ng alsa-utils \
  libwayland-dev libpango1.0-dev libxkbcommon-dev pkg-config make patch xz-utils nftables iptables \
  udisks2 polkitd gvfs-backends util-linux exfatprogs ntfs-3g firmware-realtek dnsmasq-base
apt-get install -y --no-install-recommends rpi-connect-lite qrencode

bash "${SOURCE_ROOT}/system/build-keyboard.sh" "${SOURCE_ROOT}/assets/keyboard/wvkbd_0.15.orig.tar.xz" \
  "${INSTALL_ROOT}/bin" "${INSTALL_ROOT}/third-party/wvkbd"

groupadd --system -f luma
if ! id luma >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash --gid luma --groups audio,bluetooth,input,render,video,i2c luma
fi
usermod -a -G audio,bluetooth,input,render,video,i2c luma
groupadd --system -f luma-led
usermod -a -G luma-led luma
install -m 0644 "${SOURCE_ROOT}/system/70-luma-spi.rules" /etc/udev/rules.d/

install -d -m 0755 "${INSTALL_ROOT}/backend" "${INSTALL_ROOT}/frontend"
install -d -m 0755 -o root -g root "${INSTALL_ROOT}/qualification"
install -m 0644 -o root -g root "${SOURCE_ROOT}/tests/device_smoke.py" "${INSTALL_ROOT}/qualification/device_smoke.py"
install -m 0644 -o root -g root "${SOURCE_ROOT}/tests/tailscale-status.json" "${INSTALL_ROOT}/qualification/tailscale-status.json"
cp -a "${SOURCE_ROOT}/backend/." "${INSTALL_ROOT}/backend/"
cp -a "${SOURCE_ROOT}/frontend/dist/." "${INSTALL_ROOT}/frontend/"
python3 -m venv "${INSTALL_ROOT}/venv"
"${INSTALL_ROOT}/venv/bin/pip" install --no-cache-dir "${INSTALL_ROOT}/backend[voice]"
install -d -m 0755 "${INSTALL_ROOT}/models" "${INSTALL_ROOT}/licenses" /boot/firmware/overlays
cp -a "${SOURCE_ROOT}/assets/models/vosk" "${INSTALL_ROOT}/models/"
cp -a "${SOURCE_ROOT}/assets/licenses/." "${INSTALL_ROOT}/licenses/"
install -m 0644 "${SOURCE_ROOT}/assets/overlays/respeaker-2mic-v1_0.dtbo" /boot/firmware/overlays/
install -m 0644 "${SOURCE_ROOT}/system/luma-hardware.txt" /boot/firmware/luma-hardware.txt
if ! grep -q '^include luma-hardware.txt$' /boot/firmware/config.txt; then
  printf '\n[all]\ninclude luma-hardware.txt\n' >> /boot/firmware/config.txt
fi

# Stable service paths resolve through this root-controlled, versioned release pointer.
printf '{"version":"%s"}\n' "${APP_VERSION}" > "${INSTALL_ROOT}/.luma-release.json"
chmod 0644 "${INSTALL_ROOT}/.luma-release.json"
ln -s "luma-releases/${APP_VERSION}" /opt/luma

install -m 0644 "${SOURCE_ROOT}/system/luma-api.service" /etc/systemd/system/luma-api.service
# Ship optional transport; enrollment and sharing remain off until touch setup.
install -m 0644 "${SOURCE_ROOT}/system/luma-shortcut-gateway.service" /etc/systemd/system/
printf '%s  %s\n' '9dd1e6a592a014bbaea0103167ffe299adeda4ba14e078ce9c2895364f6c4c3f' \
  "${SOURCE_ROOT}/assets/tailscale/tailscale_1.102.4_arm64.tgz" | sha256sum --check --status
install -d -m 0755 "${INSTALL_ROOT}/tailscale"
# Extract only the two pinned regular binaries, not upstream service/default files.
tar -xzf "${SOURCE_ROOT}/assets/tailscale/tailscale_1.102.4_arm64.tgz" --strip-components=1 \
  --no-same-owner -C "${INSTALL_ROOT}/tailscale" tailscale_1.102.4_arm64/tailscale tailscale_1.102.4_arm64/tailscaled
chmod 0755 "${INSTALL_ROOT}/tailscale/tailscale" "${INSTALL_ROOT}/tailscale/tailscaled"
install -m 0644 "${SOURCE_ROOT}/system/luma-tailscaled.service" \
  "${SOURCE_ROOT}/system/luma-tailscale-firewall.service" \
  "${SOURCE_ROOT}/system/luma-tailscale-setup.service" \
  "${SOURCE_ROOT}/system/luma-tailscale-setup.socket" /etc/systemd/system/
install -m 0644 "${SOURCE_ROOT}/system/luma-network.service" "${SOURCE_ROOT}/system/luma-network.socket" /etc/systemd/system/
install -m 0644 "${SOURCE_ROOT}/system/luma-backup.service" "${SOURCE_ROOT}/system/luma-backup.socket" /etc/systemd/system/
install -m 0644 "${SOURCE_ROOT}/system/luma-update.service" "${SOURCE_ROOT}/system/luma-update.socket" /etc/systemd/system/
install -d -m 0755 /usr/local/libexec
install -m 0755 "${SOURCE_ROOT}/system/luma_boot_diagnostics.py" /usr/local/libexec/luma-boot-diagnostics.py
install -m 0644 "${SOURCE_ROOT}/system/luma-boot-diagnostics.service" /etc/systemd/system/
install -d -m 0755 /etc/NetworkManager/conf.d
install -m 0644 "${SOURCE_ROOT}/system/30-luma-connectivity.conf" /etc/NetworkManager/conf.d/
# Trust is scoped to the Stanford Wi-Fi profile, never the OS/browser trust store.
printf '%s  %s\n' 'e659812ac49e4400e189115c507cf7d7d8f586adca642f8205d4815e939770e8' \
  "${SOURCE_ROOT}/backend/src/luma/assets/stanford-eduroam-ca.pem" | sha256sum --check --status
install -m 0644 -o root -g root "${SOURCE_ROOT}/system/luma-tailscale.nft" /etc/luma/tailscale.nft
install -m 0644 -o root -g root "${SOURCE_ROOT}/backend/src/luma/assets/stanford-eduroam-ca.pem" /etc/luma/stanford-eduroam-ca.pem
install -d -m 0755 /etc/wireplumber/wireplumber.conf.d
install -m 0644 "${SOURCE_ROOT}/system/80-luma-no-bluetooth-audio.conf" /etc/wireplumber/wireplumber.conf.d/
install -d -m 0755 /home/luma/.config/systemd/user
install -m 0644 "${SOURCE_ROOT}/system/luma-kiosk.service" /home/luma/.config/systemd/user/
install -m 0644 "${SOURCE_ROOT}/system/luma-device.service" /home/luma/.config/systemd/user/
install -m 0644 "${SOURCE_ROOT}/system/luma-voice.service" /home/luma/.config/systemd/user/
install -m 0644 "${SOURCE_ROOT}/system/luma-tmpfiles.conf" /usr/lib/tmpfiles.d/luma.conf
install -d -m 0755 /home/luma/.config/pipewire/pipewire.conf.d /home/luma/.config/labwc
install -m 0644 "${SOURCE_ROOT}/system/pipewire/99-luma-echo-cancel.conf" /home/luma/.config/pipewire/pipewire.conf.d/
install -m 0755 "${SOURCE_ROOT}/system/labwc-autostart" /home/luma/.config/labwc/autostart
chown -R luma:luma /home/luma/.config
# Image construction has no running systemd and may not mount /proc in chroot.
# Create the required data directory directly; tmpfiles maintains it on real boot.
install -d -m 0700 -o luma -g luma /var/lib/luma
# A build chroot can see the host's systemd PID through bind-mounted /proc,
# without having its own manager. Never contact that bus during image assembly.
if [[ ${LUMA_IMAGE_BUILD:-0} != 1 && -S /run/systemd/private && -d /run/systemd/system ]]; then
  systemctl daemon-reload
fi
install -d -m 0755 /etc/lightdm/lightdm.conf.d
install -m 0644 "${SOURCE_ROOT}/system/60-luma.conf" /etc/lightdm/lightdm.conf.d/
systemctl --root=/ enable luma-api.service luma-boot-diagnostics.service luma-network.socket luma-backup.socket luma-update.socket luma-tailscale-setup.socket bluetooth.service lightdm.service avahi-daemon.service
systemctl --root=/ set-default graphical.target

# Owner-approved recovery route. Only the public key enters the appliance.
if [[ -f "${SOURCE_ROOT}/system/luma-admin.pub" ]]; then
  apt-get install -y --no-install-recommends openssh-server sudo
  ssh-keygen -l -f "${SOURCE_ROOT}/system/luma-admin.pub" >/dev/null
  if ! id luma-admin >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash luma-admin
  fi
  install -d -m 0700 -o luma-admin -g luma-admin /home/luma-admin/.ssh
  install -m 0600 -o luma-admin -g luma-admin "${SOURCE_ROOT}/system/luma-admin.pub" /home/luma-admin/.ssh/authorized_keys
  install -d -m 0700 -o luma-admin -g luma-admin \
    /home/luma-admin/.config/com.raspberrypi.connect /home/luma-admin/.config/systemd/user \
    /home/luma-admin/.config/luma /home/luma-admin/.cache /home/luma-admin/.local/share
  # Keep the dedicated Connect shell available across logout and reboot. It is
  # still unlinked and disabled until the owner approves it on the touchscreen.
  install -d -m 0755 /var/lib/systemd/linger
  install -m 0644 -o root -g root /dev/null /var/lib/systemd/linger/luma-admin
  install -m 0440 "${SOURCE_ROOT}/system/luma-admin-sudoers" /etc/sudoers.d/luma-admin
  visudo -cf /etc/sudoers.d/luma-admin
  install -m 0644 "${SOURCE_ROOT}/system/10-luma-ssh.conf" /etc/ssh/sshd_config.d/
  install -m 0644 "${SOURCE_ROOT}/system/luma-ssh-hostkeys.service" /etc/systemd/system/
  install -m 0644 "${SOURCE_ROOT}/system/luma-pi-connect-setup.service" \
    "${SOURCE_ROOT}/system/luma-pi-connect-setup.socket" /etc/systemd/system/
  systemctl --root=/ enable luma-pi-connect-setup.socket
  systemctl --root=/ enable ssh.service luma-ssh-hostkeys.service
fi

echo "Luma runtime installed. Reboot to start the dashboard."
