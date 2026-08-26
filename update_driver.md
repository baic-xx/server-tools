# NVIDIA Driver Upgrade Notes

This note records the remote-server NVIDIA driver upgrade flow used on this machine: Ubuntu 24.04, A100 + NVSwitch, moving from an old `.run` driver install to Ubuntu apt-managed `580-server` packages.

## 0. Open a safe remote session

Use a persistent shell session before touching the driver:

```bash
tmux new -s driver-upgrade
sudo -v
```

Make sure there is a backup access path such as IPMI, iDRAC, BMC, cloud console, or on-site help.

## 1. Pre-upgrade checks

```bash
nvidia-smi
uname -r
systemctl status nvidia-fabricmanager --no-pager
dkms status
apt-mark showhold
```

Only continue after GPU training/inference jobs have stopped. `nvidia-smi` should show no important compute processes.

## 2. Disable mismatched CUDA apt source

This server was Ubuntu 24.04 but had an Ubuntu 20.04 CUDA source. Disable it before upgrading the driver so apt does not prefer mismatched NVIDIA packages.

```bash
sudo mv /etc/apt/sources.list.d/cuda-ubuntu2004-x86_64.list \
  /etc/apt/sources.list.d/cuda-ubuntu2004-x86_64.list.disabled 2>/dev/null || true

sudo apt update
```

## 3. If the old driver came from `.run`, uninstall it

Check whether a runfile installer is present:

```bash
ls -l /usr/bin/nvidia-uninstall /usr/bin/nvidia-installer 2>/dev/null || true
dpkg -S /usr/bin/nvidia-smi 2>/dev/null || true
```

If `/usr/bin/nvidia-uninstall` exists, stop Fabric Manager and uninstall the runfile driver:

```bash
sudo systemctl stop nvidia-fabricmanager
sudo /usr/bin/nvidia-uninstall
```

If the uninstaller prints this warning:

```text
WARNING: Failed to delete some directories. See /var/log/nvidia-uninstall.log for details.
```

inspect the log:

```bash
sudo tail -n 120 /var/log/nvidia-uninstall.log
```

If `nvidia-smi` is already gone and the warning is only about a non-empty directory such as `/usr/share/nvidia`, continue to apt installation. Do not reboot yet.

## 4. Simulate the new driver install

For this machine, Ubuntu 24.04 currently resolves the stable server path to `580-server`. The 570 package names are transitional and jump to 580, so use 580 explicitly:

```bash
sudo apt -s install nvidia-driver-580-server nvidia-fabricmanager-580
```

Review the simulation. Expected behavior:

- Removes old `nvidia-fabricmanager-555`.
- Installs `nvidia-driver-580-server`.
- Installs `nvidia-fabricmanager-580`.
- Uses version `580.159.03-0ubuntu0.24.04.1` or the current Ubuntu 24.04 equivalent.
- Does not remove `openssh-server`, core system packages, or OFED/Mellanox core packages.

Stop and investigate if apt wants to remove critical system packages.

## 5. Install the driver

```bash
sudo apt install nvidia-driver-580-server nvidia-fabricmanager-580
```

If DKMS builds modules, wait for it to finish. Do not interrupt the install.

If a Secure Boot or MOK prompt appears, stop and handle that explicitly before rebooting.

## 6. Hold NVIDIA packages to prevent automatic driver upgrades

Run this after the 580 packages are installed and before rebooting:

```bash
sudo apt-mark hold \
  nvidia-driver-580-server \
  nvidia-dkms-580-server \
  nvidia-kernel-common-580-server \
  nvidia-kernel-source-580-server \
  nvidia-utils-580-server \
  nvidia-compute-utils-580-server \
  nvidia-fabricmanager-580 \
  libnvidia-compute-580-server \
  libnvidia-gl-580-server \
  libnvidia-cfg1-580-server \
  libnvidia-decode-580-server \
  libnvidia-encode-580-server \
  libnvidia-extra-580-server \
  libnvidia-fbc1-580-server
```

Confirm the hold list:

```bash
apt-mark showhold | grep -E 'nvidia|libnvidia'
```

## 7. Enable Fabric Manager and reboot

```bash
sudo systemctl enable nvidia-fabricmanager
sudo reboot
```

## 8. Verify after reboot

```bash
nvidia-smi
nvidia-smi -L
systemctl status nvidia-fabricmanager --no-pager
lsmod | grep '^nvidia'
dkms status | grep -i nvidia || true
```

Expected result:

- `nvidia-smi` shows `Driver Version: 580.159.03` or the installed 580-server version.
- All A100 GPUs are listed by `nvidia-smi -L`.
- `nvidia-fabricmanager` is `active (running)`.

## 9. Unhold packages before a future intentional driver upgrade

```bash
sudo apt-mark unhold \
  nvidia-driver-580-server \
  nvidia-dkms-580-server \
  nvidia-kernel-common-580-server \
  nvidia-kernel-source-580-server \
  nvidia-utils-580-server \
  nvidia-compute-utils-580-server \
  nvidia-fabricmanager-580 \
  libnvidia-compute-580-server \
  libnvidia-gl-580-server \
  libnvidia-cfg1-580-server \
  libnvidia-decode-580-server \
  libnvidia-encode-580-server \
  libnvidia-extra-580-server \
  libnvidia-fbc1-580-server
```

## Short version

```text
tmux -> disable mismatched CUDA source -> uninstall old runfile driver -> apt simulation -> install nvidia-driver-580-server + nvidia-fabricmanager-580 -> apt-mark hold -> reboot -> verify
```
