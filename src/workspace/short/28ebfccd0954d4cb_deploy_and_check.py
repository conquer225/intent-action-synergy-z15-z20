import argparse
from pathlib import Path

import paramiko


HERE = Path(__file__).resolve().parent
PROJECT = Path("D:/ican/ican_fpga_project/GuardianLoop_Z15_2025_1")
WIFI_OUTPUT = HERE.parent / "output/z15_rtl8188eus_v2020.2"
WIFI_CFG80211_OUTPUT = HERE.parent / "output/z15_rtl8188eus_cfg80211_v2020.2"
REMOTE_DIR = "/home/xilinx/jupyter_notebooks/guardianloop_pynq"
FILES = (
    (PROJECT / "GuardianLoop_Z15_2025_1.runs/impl_1/guardianloop_bd_wrapper.bit", "guardianloop_pynq.bit"),
    (PROJECT / "GuardianLoop_Z15_2025_1.gen/sources_1/bd/guardianloop_bd/hw_handoff/guardianloop_bd.hwh", "guardianloop_pynq.hwh"),
    (HERE / "guardianloop_pynq.py", "guardianloop_pynq.py"),
    (HERE / "board_check.py", "board_check.py"),
    (HERE / "window_server.py", "window_server.py"),
    (HERE / "cyton_usb_probe.py", "cyton_usb_probe.py"),
    (HERE / "cyton_guardianloop.py", "cyton_guardianloop.py"),
    (HERE / "cyton_sqi.py", "cyton_sqi.py"),
    (HERE / "gameemo_emotion_model.json", "gameemo_emotion_model.json"),
    (HERE / "guardianloop_web.py", "guardianloop_web.py"),
    (HERE / "guardianloop-cyton.service", "guardianloop-cyton.service"),
    (HERE / "guardianloop-web.service", "guardianloop-web.service"),
    (HERE / "DEPLOYMENT.md", "DEPLOYMENT.md"),
    (HERE.parent / "tmp/rtl8188eu-linux-v5.4.tar.gz", "rtl8188eu-linux-v5.4.tar.gz"),
    (WIFI_OUTPUT / "r8188eu.ko", "r8188eu.ko"),
    (WIFI_OUTPUT / "lib80211.ko", "lib80211.ko"),
    (WIFI_OUTPUT / "rtl8188eufw.bin", "rtl8188eufw.bin"),
    (HERE / "r8188eu-test-blacklist.conf", "r8188eu-test-blacklist.conf"),
    (WIFI_CFG80211_OUTPUT / "8188eu.ko", "8188eu.ko"),
    (HERE / "guardianloop-ap.conf", "guardianloop-ap.conf"),
    (HERE / "guardianloop-dnsmasq.conf", "guardianloop-dnsmasq.conf"),
    (HERE / "guardianloop-ap.service", "guardianloop-ap.service"),
    (HERE / "guardianloop-dhcp.service", "guardianloop-dhcp.service"),
    (HERE / "guardianloop-wlan0-unmanaged.conf", "guardianloop-wlan0-unmanaged.conf"),
)


def main():
    parser = argparse.ArgumentParser(description="Deploy existing GuardianLoop bit/HWH to Z15 PYNQ")
    parser.add_argument("--host", default="192.168.2.99")
    parser.add_argument("--user", default="xilinx")
    parser.add_argument("--password", default="xilinx")
    parser.add_argument("--upload-only", action="store_true",
                        help="upload new files without rerunning the hardware check")
    parser.add_argument("--cyton-test", action="store_true",
                        help="run one direct Cyton-to-GuardianLoop window after upload")
    parser.add_argument("--install-service", action="store_true",
                        help="install the Cyton service but leave it disabled and stopped")
    parser.add_argument("--install-web-service", action="store_true",
                        help="install and enable the board-local dashboard, leaving Cyton disabled")
    parser.add_argument("--install-ap-services", action="store_true",
                        help="configure the Z15 as the GuardianLoop-Z15 Wi-Fi access point")
    parser.add_argument("--wifi-check", action="store_true",
                        help="inspect Wi-Fi USB hardware, kernel modules, and network tools")
    parser.add_argument("--install-wifi-driver", action="store_true",
                        help="build and install the in-tree RTL8188EUS staging driver")
    parser.add_argument("--install-prebuilt-wifi-driver", action="store_true",
                        help="install the exact cross-built RTL8188EUS module and firmware")
    parser.add_argument("--stage-fixed-wifi-driver", action="store_true",
                        help="stage fixed module with automatic USB binding blocked until tested")
    parser.add_argument("--install-cfg80211-wifi-driver", action="store_true",
                        help="install and test the RTL8188EUS cfg80211 driver")
    parser.add_argument("--bind-wifi-driver", action="store_true",
                        help="test-bind RTL8188EUS to the existing rtl8xxxu driver")
    parser.add_argument("--download-kernel-build-info", action="store_true",
                        help="download the running kernel config and Module.symvers")
    args = parser.parse_args()
    for source, _ in FILES:
        if not source.is_file():
            raise FileNotFoundError(source)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(args.host, username=args.user, password=args.password, timeout=10)
    try:
        if args.download_kernel_build_info:
            destination = HERE.parent / "tmp/z15-kernel-v2020.2"
            destination.mkdir(parents=True, exist_ok=True)
            with client.open_sftp() as sftp:
                sftp.get("/proc/config.gz", str(destination / "config.gz"))
                try:
                    sftp.get("/lib/modules/5.4.0-xilinx-v2020.2/build/Module.symvers",
                             str(destination / "Module.symvers"))
                except FileNotFoundError:
                    print("Module.symvers=missing")
            print(f"kernel_build_info={destination}")
            return

        _, stdout, stderr = client.exec_command(f"mkdir -p {REMOTE_DIR}", timeout=10)
        if stdout.channel.recv_exit_status() != 0:
            raise RuntimeError(stderr.read().decode("utf-8", errors="replace"))
        with client.open_sftp() as sftp:
            for source, name in FILES:
                target = f"{REMOTE_DIR}/{name}"
                sftp.put(str(source), target)
                print(f"uploaded={target}")

        if args.stage_fixed_wifi_driver:
            command = (f"printf '%s\\n' {args.password} | sudo -S sh -c '"
                       "set -e; test \"$(uname -r)\" = 5.4.0-xilinx-v2020.2; "
                       "module_dir=/lib/modules/$(uname -r)/kernel/drivers/staging/rtl8188eu; "
                       "mkdir -p $module_dir /lib/firmware/rtlwifi; "
                       "install -m 0644 "
                       f"{REMOTE_DIR}/r8188eu-test-blacklist.conf /etc/modprobe.d/r8188eu-test-blacklist.conf; "
                       "if [ -e $module_dir/r8188eu.ko ] && "
                       "[ ! -e $module_dir/r8188eu.ko.before-fixed-layout ]; then "
                       "cp -a $module_dir/r8188eu.ko $module_dir/r8188eu.ko.before-fixed-layout; fi; "
                       f"install -m 0644 {REMOTE_DIR}/r8188eu.ko $module_dir/r8188eu.ko; "
                       f"install -m 0644 {REMOTE_DIR}/rtl8188eufw.bin "
                       "/lib/firmware/rtlwifi/rtl8188eufw.bin; "
                       "depmod -a; echo FIXED_MODULE_STAGED_AUTOLOAD_BLOCKED; "
                       "modinfo r8188eu | grep -E \"^(filename|vermagic|firmware):\"'")
            _, stdout, stderr = client.exec_command(command, timeout=30)
            output = stdout.read().decode("utf-8", errors="replace")
            errors = stderr.read().decode("utf-8", errors="replace")
            status = stdout.channel.recv_exit_status()
            print(output, end="" if output.endswith("\n") else "\n")
            if errors:
                print(errors, end="" if errors.endswith("\n") else "\n")
            if status != 0:
                raise SystemExit(status)
            return

        if args.install_cfg80211_wifi_driver:
            command = (f"printf '%s\\n' {args.password} | sudo -S sh -c '"
                       "set -e; test \"$(uname -r)\" = 5.4.0-xilinx-v2020.2; "
                       "module_dir=/lib/modules/$(uname -r)/kernel/drivers/net/wireless/8188eu; "
                       "mkdir -p $module_dir /etc/modprobe.d; "
                       f"install -m 0644 {REMOTE_DIR}/8188eu.ko $module_dir/8188eu.ko; "
                       "printf \"blacklist r8188eu\\nblacklist rtl8xxxu\\n\" "
                       "> /etc/modprobe.d/guardianloop-rtl8188eus.conf; "
                       "depmod -a; modprobe -r r8188eu rtl8xxxu 2>/dev/null || true; "
                       "modprobe 8188eu; sleep 5; "
                       "echo CFG80211_DRIVER_TESTED; "
                       "modinfo 8188eu | grep -E \"^(filename|version|vermagic|depends):\"; "
                       "echo NETWORK; ip -brief link; echo WIRELESS; iw dev; "
                       "echo USB_DRIVER; for device in /sys/bus/usb/devices/*; do "
                       "[ \"$(cat $device/idVendor 2>/dev/null)\" = 0bda ] || continue; "
                       "[ \"$(cat $device/idProduct 2>/dev/null)\" = 8179 ] || continue; "
                       "readlink -f $device/driver || true; done; "
                       "echo DMESG; dmesg | tail -n 45'")
            _, stdout, stderr = client.exec_command(command, timeout=90)
            output = stdout.read().decode("utf-8", errors="replace")
            errors = stderr.read().decode("utf-8", errors="replace")
            status = stdout.channel.recv_exit_status()
            print(output, end="" if output.endswith("\n") else "\n")
            if errors:
                print(errors, end="" if errors.endswith("\n") else "\n")
            if status != 0:
                raise SystemExit(status)
            return

        if args.bind_wifi_driver:
            command = (f"printf '%s\\n' {args.password} | sudo -S sh -c '"
                       "set -e; modprobe rtl8xxxu; "
                       "if [ -w /sys/bus/usb/drivers/rtl8xxxu/new_id ]; then "
                       "echo 0bda 8179 > /sys/bus/usb/drivers/rtl8xxxu/new_id; fi; "
                       "for device in /sys/bus/usb/devices/*; do "
                       "[ -f $device/idVendor ] || continue; "
                       "[ $(cat $device/idVendor) = 0bda ] || continue; "
                       "[ $(cat $device/idProduct) = 8179 ] || continue; "
                       "basename $device > /sys/bus/usb/drivers_probe; done; "
                       "sleep 3; echo RTL8XXXU_DYNAMIC_BIND_DONE; ip -brief link; iw dev; "
                       "dmesg | tail -n 35'")
            _, stdout, stderr = client.exec_command(command, timeout=40)
            output = stdout.read().decode("utf-8", errors="replace")
            errors = stderr.read().decode("utf-8", errors="replace")
            status = stdout.channel.recv_exit_status()
            print(output, end="" if output.endswith("\n") else "\n")
            if errors:
                print(errors, end="" if errors.endswith("\n") else "\n")
            if status != 0:
                raise SystemExit(status)
            return

        if args.install_wifi_driver:
            command = (f"printf '%s\\n' {args.password} | sudo -S sh -c '"
                       "set -e; kernel=$(uname -r); tree=/lib/modules/$kernel/build; "
                       f"tar -xzf {REMOTE_DIR}/rtl8188eu-linux-v5.4.tar.gz -C $tree; "
                       "make -C $tree modules_prepare; "
                       "make -C $tree M=drivers/staging/rtl8188eu CONFIG_R8188EU=m modules; "
                       "mkdir -p /lib/modules/$kernel/kernel/drivers/staging/rtl8188eu; "
                       "install -m 0644 $tree/drivers/staging/rtl8188eu/r8188eu.ko "
                       "/lib/modules/$kernel/kernel/drivers/staging/rtl8188eu/r8188eu.ko; "
                       "depmod -a; modprobe r8188eu; sleep 2; "
                       "echo RTL8188EUS_DRIVER_INSTALLED; ip -brief link; iw dev'")
            _, stdout, stderr = client.exec_command(command, timeout=600)
            output = stdout.read().decode("utf-8", errors="replace")
            errors = stderr.read().decode("utf-8", errors="replace")
            status = stdout.channel.recv_exit_status()
            print(output, end="" if output.endswith("\n") else "\n")
            if errors:
                print(errors, end="" if errors.endswith("\n") else "\n")
            if status != 0:
                raise SystemExit(status)
            return

        if args.install_prebuilt_wifi_driver:
            command = (f"printf '%s\\n' {args.password} | sudo -S sh -c '"
                       "set -e; kernel=$(uname -r); "
                       "test \"$kernel\" = 5.4.0-xilinx-v2020.2; "
                       "module_dir=/lib/modules/$kernel/kernel/drivers/staging/rtl8188eu; "
                       "wireless_dir=/lib/modules/$kernel/kernel/net/wireless; "
                       "firmware_dir=/lib/firmware/rtlwifi; "
                       "mkdir -p $module_dir $wireless_dir $firmware_dir; "
                       "[ ! -e $module_dir/r8188eu.ko ] || "
                       "cp -a $module_dir/r8188eu.ko $module_dir/r8188eu.ko.before-codex; "
                       "[ ! -e $firmware_dir/rtl8188eufw.bin ] || "
                       "cp -a $firmware_dir/rtl8188eufw.bin $firmware_dir/rtl8188eufw.bin.before-codex; "
                       f"install -m 0644 {REMOTE_DIR}/r8188eu.ko $module_dir/r8188eu.ko; "
                       f"install -m 0644 {REMOTE_DIR}/lib80211.ko $wireless_dir/lib80211.ko; "
                       f"install -m 0644 {REMOTE_DIR}/rtl8188eufw.bin $firmware_dir/rtl8188eufw.bin; "
                       "depmod -a; modprobe -r rtl8xxxu 2>/dev/null || true; "
                       "modprobe lib80211; "
                       "if ! modprobe r8188eu; then echo MODPROBE_FAILED; lsmod | grep 80211 || true; "
                       "modinfo lib80211 2>&1 || true; dmesg | tail -n 50; exit 1; fi; sleep 3; "
                       "echo R8188EU_INSTALLED; modinfo r8188eu | grep -E \"^(filename|version|vermagic|firmware):\"; "
                       "echo NETWORK; ip -brief link; echo WIRELESS; iw dev; "
                       "echo USB_DRIVER; for device in /sys/bus/usb/devices/*; do "
                       "[ \"$(cat $device/idVendor 2>/dev/null)\" = 0bda ] || continue; "
                       "[ \"$(cat $device/idProduct 2>/dev/null)\" = 8179 ] || continue; "
                       "readlink -f $device/driver || true; done; "
                       "echo DMESG; dmesg | tail -n 35'")
            _, stdout, stderr = client.exec_command(command, timeout=90)
            output = stdout.read().decode("utf-8", errors="replace")
            errors = stderr.read().decode("utf-8", errors="replace")
            status = stdout.channel.recv_exit_status()
            print(output, end="" if output.endswith("\n") else "\n")
            if errors:
                print(errors, end="" if errors.endswith("\n") else "\n")
            if status != 0:
                raise SystemExit(status)
            return

        if args.wifi_check:
            cmd = ("uname -a; echo MODULE_FILES; "
                   "find /lib/modules/$(uname -r) -type f | grep -Ei '8188|8192|rtl8|realtek' | head -80; "
                   "echo KERNEL_CONFIG; "
                   "zgrep -E 'CONFIG_RTL8|CONFIG_88XX|CONFIG_WLAN_VENDOR_REALTEK' /proc/config.gz 2>/dev/null || true; "
                   "echo TOOLS; command -v nmcli || true; command -v wpa_supplicant || true; "
                   "command -v gcc || true; ls -ld /lib/modules/$(uname -r)/build 2>/dev/null || true; "
                   "echo RTL8XXXU_8179_ALIAS; modinfo rtl8xxxu 2>/dev/null | grep -i 8179 || true; "
                   "echo USB; lsusb; echo NETWORK; ip -brief link")
            _, stdout, stderr = client.exec_command(cmd, timeout=20)
            output = stdout.read().decode("utf-8", errors="replace")
            errors = stderr.read().decode("utf-8", errors="replace")
            status = stdout.channel.recv_exit_status()
            print(output, end="" if output.endswith("\n") else "\n")
            if errors:
                print(errors, end="" if errors.endswith("\n") else "\n")
            if status != 0:
                raise SystemExit(status)
            return

        if args.install_service:
            cmd = (f"printf '%s\\n' {args.password} | sudo -S install -m 0644 "
                   f"{REMOTE_DIR}/guardianloop-cyton.service /etc/systemd/system/guardianloop-cyton.service && "
                   "sudo systemctl daemon-reload && sudo systemctl disable guardianloop-cyton.service; "
                   "echo GUARDIANLOOP_SERVICE_INSTALLED_DISABLED; "
                   "systemctl is-enabled guardianloop-cyton.service || true; "
                   "systemctl is-active guardianloop-cyton.service || true; "
                   "ip -brief link; echo USB_DEVICES; lsusb")
            _, stdout, stderr = client.exec_command(cmd, timeout=20)
            output = stdout.read().decode("utf-8", errors="replace")
            errors = stderr.read().decode("utf-8", errors="replace")
            status = stdout.channel.recv_exit_status()
            print(output, end="" if output.endswith("\n") else "\n")
            if errors:
                print(errors, end="" if errors.endswith("\n") else "\n")
            if status != 0:
                raise SystemExit(status)
            return

        if args.install_web_service:
            cmd = (f"printf '%s\\n' {args.password} | sudo -S sh -c '"
                   "set -e; install -m 0644 "
                   f"{REMOTE_DIR}/guardianloop-web.service /etc/systemd/system/guardianloop-web.service; "
                   "systemctl daemon-reload; systemctl enable guardianloop-web.service; "
                   "systemctl restart guardianloop-web.service; "
                   "echo WEB_SERVICE; systemctl is-active guardianloop-web.service; "
                   "echo LOCAL_API; n=0; until curl -fsS http://127.0.0.1:9102/api/status 2>/dev/null; do "
                   "n=$((n+1)); [ $n -lt 10 ] || exit 1; sleep 1; done'")
            _, stdout, stderr = client.exec_command(cmd, timeout=30)
            output = stdout.read().decode("utf-8", errors="replace")
            errors = stderr.read().decode("utf-8", errors="replace")
            status = stdout.channel.recv_exit_status()
            print(output, end="" if output.endswith("\n") else "\n")
            if errors:
                print(errors, end="" if errors.endswith("\n") else "\n")
            if status != 0:
                raise SystemExit(status)
            return

        if args.install_ap_services:
            cmd = (f"printf '%s\\n' {args.password} | sudo -S sh -c '"
                   "set -e; mkdir -p /etc/guardianloop /etc/NetworkManager/conf.d; "
                   f"install -m 0600 {REMOTE_DIR}/guardianloop-ap.conf /etc/guardianloop/ap.conf; "
                   f"install -m 0644 {REMOTE_DIR}/guardianloop-dnsmasq.conf /etc/guardianloop/dnsmasq.conf; "
                   f"install -m 0644 {REMOTE_DIR}/guardianloop-wlan0-unmanaged.conf "
                   "/etc/NetworkManager/conf.d/99-guardianloop-wlan0-unmanaged.conf; "
                   f"install -m 0644 {REMOTE_DIR}/guardianloop-ap.service "
                   "/etc/systemd/system/guardianloop-ap.service; "
                   f"install -m 0644 {REMOTE_DIR}/guardianloop-dhcp.service "
                   "/etc/systemd/system/guardianloop-dhcp.service; "
                   "printf \"8188eu\\n\" > /etc/modules-load.d/guardianloop-8188eu.conf; "
                   "systemctl daemon-reload; "
                   "systemctl enable guardianloop-ap.service guardianloop-dhcp.service; "
                   "systemctl restart guardianloop-ap.service; sleep 4; "
                   "echo AP_STATE; systemctl is-active guardianloop-ap.service; "
                   "echo DHCP_STATE; systemctl is-active guardianloop-dhcp.service; "
                   "echo WLAN; iw dev; ip -4 addr show wlan0; "
                   "echo LISTEN; ss -lntup | grep -E \":(67|9102)\\b\" || true'")
            _, stdout, stderr = client.exec_command(cmd, timeout=60)
            output = stdout.read().decode("utf-8", errors="replace")
            errors = stderr.read().decode("utf-8", errors="replace")
            status = stdout.channel.recv_exit_status()
            print(output, end="" if output.endswith("\n") else "\n")
            if errors:
                print(errors, end="" if errors.endswith("\n") else "\n")
            if status != 0:
                raise SystemExit(status)
            return

        if args.upload_only:
            return

        remote_script = ("cyton_guardianloop.py --windows 1 --allow-clipping"
                         if args.cyton_test else "board_check.py")
        cmd = (f"printf '%s\\n' {args.password} | sudo -S env XILINX_XRT=/usr "
               f"timeout 35s /usr/local/share/pynq-venv/bin/python3 {REMOTE_DIR}/{remote_script}")
        _, stdout, stderr = client.exec_command(cmd, timeout=45)
        output = stdout.read().decode("utf-8", errors="replace")
        errors = stderr.read().decode("utf-8", errors="replace")
        status = stdout.channel.recv_exit_status()
        print(output, end="" if output.endswith("\n") else "\n")
        if errors:
            print(errors, end="" if errors.endswith("\n") else "\n")
        print(f"remote_exit={status}")
        if status != 0:
            raise SystemExit(status)
    finally:
        client.close()


if __name__ == "__main__":
    main()
