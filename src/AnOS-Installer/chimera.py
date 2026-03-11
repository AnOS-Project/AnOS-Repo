#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import shutil
import time
import socket
import shlex
import glob
import json

# --- Configuration & Constants ---
COLORS = {
    'HEADER': '\033[95m', 'BLUE': '\033[94m', 'GREEN': '\033[92m',
    'WARN': '\033[93m', 'FAIL': '\033[91m', 'ENDC': '\033[0m', 'BOLD': '\033[1m'
}
MOUNT_POINT = "/mnt/anos_target"
DEBUG_MODE = False

# --- Utility Functions ---
def log(msg, level="info"):
    icon = "[*]"
    color = COLORS['BLUE']
    if level == "error": icon, color = "[!]", COLORS['FAIL']
    elif level == "success": icon, color = "[+]", COLORS['GREEN']
    elif level == "warn": icon, color = "[?]", COLORS['WARN']
    elif level == "HEADER": icon, color = "[#]", COLORS['HEADER']
    elif level == "DEBUG": icon, color = "[D]", COLORS['WARN']
    
    print(f"{color}{icon} {msg}{COLORS['ENDC']}")

def run_cmd(cmd, shell=False, check=True, chroot=False, ignore_error=False, env=None, stream=False):
    show_output = stream or DEBUG_MODE

    if chroot:
        if isinstance(cmd, list): cmd_str = " ".join(shlex.quote(arg) for arg in cmd)
        else: cmd_str = cmd
        
        if shutil.which("arch-chroot"):
            cmd =["arch-chroot", MOUNT_POINT, "/bin/sh", "-c", cmd_str]
        else:
            cmd = ["chroot", MOUNT_POINT, "/bin/sh", "-c", cmd_str]
        shell = False
    
    if DEBUG_MODE:
        log(f"CMD: {cmd}", "DEBUG")

    try:
        if show_output:
            proc = subprocess.run(cmd, shell=shell, check=check, env=env)
        else:
            proc = subprocess.run(cmd, shell=shell, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        return proc.returncode == 0
    except subprocess.CalledProcessError as e:
        if not ignore_error:
            log(f"Command Failed: {cmd}", "error")
            if e.stderr:
                print(f"{COLORS['FAIL']}STDERR: {e.stderr.decode().strip()}{COLORS['ENDC']}")
            elif show_output:
                print(f"{COLORS['FAIL']}(Command failed, output above){COLORS['ENDC']}")
            if check: raise e 
        return False

def check_connection():
    """Kiểm tra kết nối mạng (BƯỚC 1 - Treemap)"""
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=3)
        return True
    except OSError:
        return False

def get_blk_value(device, field):
    try:
        return subprocess.check_output(["lsblk", "-no", field, device], stderr=subprocess.DEVNULL).decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""

def get_ram_gb():
    """Lấy dung lượng RAM để tính Swap = RAM / 2"""
    try:
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if 'MemTotal' in line:
                    return max(1, int(line.split()[1]) // 1048576)
    except Exception:
        pass
    return 4 # Mặc định nếu không đọc được là 4GB

def detect_nvidia():
    """Nhận diện Card NVIDIA"""
    try:
        out = subprocess.check_output(["lspci"]).decode().lower()
        return "nvidia" in out and ("vga" in out or "3d" in out)
    except:
        return False

# --- Main Installer Class ---
class AnOSInstaller:
    def __init__(self, args):
        self.args = args
        self.uefi = os.path.exists("/sys/firmware/efi")
        self.target_os = args.target.lower()
        self.disk = args.disk if args.disk else self._detect_disk(args.rootfs)
        self.is_online = check_connection()
        
        if self.args.user and not self.args.passwd:
            sys.exit(f"{COLORS['FAIL']}Error: --user requires --passwd{COLORS['ENDC']}")

    def _detect_disk(self, partition):
        try:
            if not partition: return None
            parent = subprocess.check_output(["lsblk", "-no", "pkname", partition], stderr=subprocess.PIPE).decode().strip()
            return f"/dev/{parent}"
        except Exception:
            return None

    def run(self):
        try:
            self.welcome()
            self.safety_check()
            self.partition_handler()
            self.install_base()
            if not shutil.which("arch-chroot"):
                self.setup_chroot_mounts()
            self.configure_system()
            self.setup_users()
            self.install_packages()
            self.install_bootloader()
            self.run_custom_scripts()
            self.finalize()
            log("AnOS Installation Successfully Completed.", "success")
        except Exception as e:
            log(f"Critical Failure: {e}", "error")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            self.cleanup()

    def welcome(self):
        os.system("clear")
        log(f"AnOS Installer - The Simple & Powerful OS", "HEADER")
        log(f"Network Status: {'Online' if self.is_online else 'Offline (Fallback Mode)'}", "info")
        log(f"Profiles Selected: {self.args.profiles}", "info")
        log(f"Target Disk: {self.disk} | Boot Mode: {'UEFI' if self.uefi else 'BIOS'}", "info")
        
        if self.args.disk:
            log("Disk Mode: WIPE WHOLE DISK", "warn")
        elif self.args.shrink_part:
            log(f"Disk Mode: DUAL BOOT (Shrink {self.args.shrink_part} by {self.args.anos_size}GB)", "warn")
        else:
            log("Disk Mode: MANUAL PARTITIONING", "warn")
            
        time.sleep(2)

    def safety_check(self):
        if self.args.i_am_very_stupid: return

        if self.args.disk:
            print(f"\n{COLORS['FAIL']}!!!!!!!!!! CẢNH BÁO ĐỎ !!!!!!!!!!{COLORS['ENDC']}")
            print(f"{COLORS['FAIL']}TOÀN BỘ DỮ LIỆU TRÊN Ổ {self.args.disk} SẼ BỊ XÓA SẠCH VÀ FORMAT.{COLORS['ENDC']}")
        elif self.args.shrink_part:
            print(f"\n{COLORS['FAIL']}CẢNH BÁO: DUAL BOOT MODE{COLORS['ENDC']}")
            print(f"Sẽ thu nhỏ phân vùng Windows {self.args.shrink_part}. Vui lòng đảm bảo đã tắt BitLocker/Fast Startup.")
        else:
            print(f"\n{COLORS['FAIL']}CẢNH BÁO: MANUAL MODE{COLORS['ENDC']}")

        if input(f"\nGõ 'YES' để tiếp tục: ") != "YES":
            sys.exit("Đã hủy bỏ (Aborted).")

    def partition_handler(self):
        log("Preparing Partitions...", "info")
        run_cmd(["umount", "-R", MOUNT_POINT], check=False, ignore_error=True)
        run_cmd(["swapoff", "-a"], check=False, ignore_error=True)
        
        if self.args.disk:
            self._auto_partition_disk()
        elif self.args.shrink_part:
            self._dual_boot_shrink()

        # Format & Mount Root
        run_cmd(["mkfs.ext4", "-F", self.args.rootfs])
        os.makedirs(MOUNT_POINT, exist_ok=True)
        run_cmd(["mount", self.args.rootfs, MOUNT_POINT])
        
        # Format & Mount Boot (If not sharing Windows EFI)
        if self.args.boot:
            path = f"{MOUNT_POINT}/boot/efi" if self.uefi else f"{MOUNT_POINT}/boot"
            os.makedirs(path, exist_ok=True)
            # Không format vfat nếu đang tái sử dụng EFI của Windows, chỉ mount
            if self.args.shrink_part and self.uefi:
                log(f"Tái sử dụng EFI Partition: {self.args.boot}", "info")
            else:
                if self.uefi: run_cmd(["mkfs.vfat", "-F32", self.args.boot])
                else: run_cmd(["mkfs.ext4", "-F", self.args.boot])
            
            run_cmd(["mount", self.args.boot, path])
        
        # Setup Swap
        if self.args.swap:
            run_cmd(["mkswap", self.args.swap])
            run_cmd(["swapon", self.args.swap])

    def _auto_partition_disk(self):
        log(f"Wiping and partitioning {self.args.disk}...", "warn")
        label_type = "gpt" if self.uefi else "msdos"
        run_cmd(["wipefs", "--all", self.disk])
        run_cmd(["parted", "-s", self.disk, "mklabel", label_type])
        
        boot_part_end = "513MiB"
        run_cmd(["parted", "-s", self.disk, "mkpart", "primary", "1MiB", boot_part_end])
        current_end = boot_part_end
        
        # Logic: Swap = RAM / 2
        ram_gb = get_ram_gb()
        swap_gb = max(1, ram_gb // 2)
        swap_end = f"{513 + (swap_gb * 1024)}MiB"
        
        log(f"Tạo Swap Partition: {swap_gb}GB", "info")
        run_cmd(["parted", "-s", self.disk, "mkpart", "primary", current_end, swap_end])
        current_end = swap_end

        # Rootfs uses remaining 100%
        run_cmd(["parted", "-s", self.disk, "mkpart", "primary", current_end, "100%"])
        
        prefix = f"{self.disk}p" if self.disk.startswith("/dev/nvme") or self.disk.startswith("/dev/mmc") else f"{self.disk}"
        
        self.args.boot = f"{prefix}1"
        self.args.swap = f"{prefix}2"
        self.args.rootfs = f"{prefix}3"

        if self.uefi: run_cmd(["parted", "-s", self.disk, "set", "1", "esp", "on"])
        else: run_cmd(["parted", "-s", self.disk, "set", "1", "boot", "on"])
        
        run_cmd(["partprobe", self.disk])
        time.sleep(2)
        log(f"Layout Auto: Boot={self.args.boot}, Swap={self.args.swap}, Root={self.args.rootfs}", "success")

    def _dual_boot_shrink(self):
        """Logic Thu nhỏ ổ Windows và tạo không gian cho AnOS"""
        log(f"Tiến hành Dual Boot Shrink trên {self.args.shrink_part}...", "warn")
        disk = self._detect_disk(self.args.shrink_part)
        anos_size_mb = int(self.args.anos_size) * 1024
        
        # 1. Thu nhỏ NTFS File System
        run_cmd(["ntfsfix", self.args.shrink_part], ignore_error=True)
        # Lấy size hiện tại (giả lập logic, thực tế cần check size kỹ càng)
        # Note: Đây là mã khung execution. Do ntfsresize cần precise bytes, ở đây ta dùng params chuẩn.
        log("Đang Resize NTFS... quá trình này có thể mất thời gian.", "info")
        run_cmd(["ntfsresize", "-f", "-s", f"-{anos_size_mb}M", self.args.shrink_part], stream=True)
        
        # 2. Resize Partition Boundary bằng parted
        part_num = self.args.shrink_part.replace(disk, "").replace("p", "")
        # Get start/end (Pseudo-logic cho Backend Script)
        run_cmd(["parted", "-s", disk, "resizepart", part_num, f"-{anos_size_mb}MB"])
        
        # 3. Tạo Swap (RAM / 2) và RootFS ở vùng trống (Free Space)
        ram_gb = get_ram_gb()
        swap_gb = max(1, ram_gb // 2)
        
        # Dùng mkpart trong free space
        run_cmd(["parted", "-s", disk, "mkpart", "primary", "linux-swap", f"-{anos_size_mb}MB", f"-{anos_size_mb - swap_gb*1024}MB"])
        run_cmd(["parted", "-s", disk, "mkpart", "primary", "ext4", f"-{anos_size_mb - swap_gb*1024}MB", "100%"])
        run_cmd(["partprobe", disk])
        time.sleep(2)
        
        # Mapping (Giả sử nó tạo ra 2 phân vùng cuối)
        out = subprocess.check_output(["lsblk", "-lnP", "-o", "NAME", disk]).decode().strip().split('\n')
        parts =[f"/dev/{line.split('=\"')[1].replace('\"','')}" for line in out]
        self.args.swap = parts[-2]
        self.args.rootfs = parts[-1]
        
        # Tìm phân vùng EFI của Windows để xài ké
        if self.uefi:
            try:
                efi_part = subprocess.check_output("lsblk -o NAME,PARTTYPE -J", shell=True).decode()
                # Tìm part có type là c12a7328-f81f-11d2-ba4b-00a0c93ec93b (EFI)
                # Đơn giản hóa trong script:
                self.args.boot = subprocess.check_output(f"fdisk -l {disk} | grep EFI | awk '{{print $1}}'", shell=True).decode().strip()
            except:
                log("Không tìm thấy EFI tự động, vui lòng cẩn thận.", "warn")

        log(f"Layout Dual Boot: Boot(Shared)={self.args.boot}, Swap={self.args.swap}, Root={self.args.rootfs}", "success")

    def install_base(self):
        log(f"Cài đặt Base System AnOS (Clone via Rsync)...", "info")
        # Base hệ thống AnOS luôn dùng Rsync bung ra (giống Triết lý BAL/Offline)
        excludes =["--exclude=/proc/*", "--exclude=/sys/*", "--exclude=/dev/*", 
                    "--exclude=/run/*", "--exclude=/tmp/*", "--exclude=/mnt/*", 
                    f"--exclude={MOUNT_POINT}/*"]
        subprocess.run(["rsync", "-axHAWXS", "--numeric-ids", "--info=progress2"] + excludes + ["/", MOUNT_POINT], check=True)

    def setup_chroot_mounts(self):
        log("Mounting API filesystems...", "info")
        for m in["dev", "proc", "sys"]:
            target = os.path.join(MOUNT_POINT, m)
            os.makedirs(target, exist_ok=True)
            run_cmd(["mount", "--rbind", f"/{m}", target], ignore_error=True)
            run_cmd(["mount", "--make-rslave", target], ignore_error=True)
        shutil.copy("/etc/resolv.conf", f"{MOUNT_POINT}/etc/resolv.conf")

    def configure_system(self):
        log("Configuring System...", "info")
        
        log(f"Setting hostname to '{self.args.host if hasattr(self.args, 'host') else 'AnOS'}'...", "info")
        with open(f"{MOUNT_POINT}/etc/hostname", "w") as f:
            f.write(f"{self.args.host if hasattr(self.args, 'host') else 'AnOS'}\n")
        
        # Timezone
        tz = self.args.timezone if self.args.timezone else "Asia/Ho_Chi_Minh"
        tz_path = f"/usr/share/zoneinfo/{tz}"
        if os.path.exists(f"{MOUNT_POINT}{tz_path}"):
            log(f"Setting timezone to {tz}...", "info")
            run_cmd(f"ln -sf {tz_path} /etc/localtime", chroot=True)
            run_cmd("hwclock --systohc", chroot=True, ignore_error=True)

        # Keyboard & Locale
        run_cmd("echo 'en_US.UTF-8 UTF-8' > /etc/locale.gen", chroot=True)
        run_cmd("locale-gen", chroot=True)
        run_cmd("echo 'LANG=en_US.UTF-8' > /etc/locale.conf", chroot=True)
        # Giả định keyboard layout US default
        run_cmd("echo 'KEYMAP=us' > /etc/vconsole.conf", chroot=True)

        # Enable Network
        run_cmd("systemctl enable NetworkManager", chroot=True, ignore_error=True)

        # Trích xuất & Cài đặt Kernel (Vì dùng Rsync từ ISO đang chạy)
        log("Extracting and building Kernel initramfs...", "info")
        kernel_dst = f"{MOUNT_POINT}/boot/vmlinuz-linux"
        os.makedirs(os.path.dirname(kernel_dst), exist_ok=True)
        search_patterns =["/usr/lib/modules/*/vmlinuz", "/boot/vmlinuz-linux", "/run/archiso/bootmnt/arch/boot/x86_64/vmlinuz-linux"]
        
        kernel_src = next((glob.glob(p)[0] for p in search_patterns if glob.glob(p)), None)
        if kernel_src:
            shutil.copy(kernel_src, kernel_dst)
            os.chmod(kernel_dst, 0o644)
        
        # Xóa preset Archiso rác
        run_cmd("rm -f /etc/mkinitcpio.conf.d/archiso.conf", chroot=True, ignore_error=True)
        
        # Sửa cấu hình hook cơ bản
        conf_path = f"{MOUNT_POINT}/etc/mkinitcpio.conf"
        try:
            with open(conf_path, 'r') as f: config_data = f.read()
            if "archiso" in config_data:
                config_data = config_data.replace("archiso", "block filesystems fsck")
                with open(conf_path, 'w') as f: f.write(config_data)
        except Exception: pass

        run_cmd("mkinitcpio -P", chroot=True, stream=True)

        # GHI LẠI FILE /etc/installation-type ĐỂ WELCOME APP BIẾT
        log("Ghi nhận thông tin Installation Type...", "info")
        with open(f"{MOUNT_POINT}/etc/installation-type", "w") as f:
            f.write(f"ONLINE={self.is_online}\n")
            f.write(f"PROFILES={self.args.profiles}\n")

        # Sinh file fstab
        self._gen_fstab()

    def setup_users(self):
        pwd = self.args.passwd
        if pwd:
            log("Setting ROOT password...", "info")
            run_cmd(f"echo 'root:{pwd}' | chpasswd", chroot=True)

        if self.args.user:
            user = self.args.user
            log(f"Creating user '{user}'...", "info")
            run_cmd(f"useradd -m -G wheel -s /bin/bash {user}", chroot=True, ignore_error=True)
            if pwd:
                run_cmd(f"echo '{user}:{pwd}' | chpasswd", chroot=True)

            log("Configuring sudo access...", "info")
            run_cmd("sed -i 's/^# %wheel ALL=(ALL:ALL) ALL/%wheel ALL=(ALL:ALL) ALL/' /etc/sudoers", chroot=True, ignore_error=True)

    def install_packages(self):
        """Xử lý cài đặt packages online theo profile và giải quyết NVIDIA Final Boss"""
        if self.is_online and self.args.packages:
            log("Online Mode: Khởi tạo Pacman Keyring & Cài đặt phần mềm theo Profile...", "HEADER")
            run_cmd("pacman-key --init", chroot=True)
            run_cmd("pacman-key --populate", chroot=True)
            run_cmd("pacman -Sy", chroot=True)
            
            pkgs = self.args.packages.replace(',', ' ')
            log(f"Đang cài đặt các packages: {pkgs}", "info")
            run_cmd(f"pacman -S --noconfirm {pkgs}", chroot=True, stream=True)
        else:
            log("Offline Mode hoặc Không có packages. Việc cài đặt Profile sẽ được Welcome App đảm nhận sau.", "warn")

        # --- NVIDIA FINAL BOSS ---
        log("Kiểm tra GPU NVIDIA...", "info")
        if detect_nvidia():
            log(">>> PHÁT HIỆN CARD NVIDIA. Kích hoạt Mainline Driver... <<<", "HEADER")
            if self.is_online:
                run_cmd("pacman -S --noconfirm nvidia nvidia-utils nvidia-settings", chroot=True, stream=True)
            self.has_nvidia = True
        else:
            self.has_nvidia = False

    def _gen_fstab(self):
        if shutil.which("genfstab"):
            with open(f"{MOUNT_POINT}/etc/fstab", "w") as f:
                subprocess.run(["genfstab", "-U", MOUNT_POINT], stdout=f)
        else:
            log("Generating fstab manually...", "info")
            root_uuid = get_blk_value(self.args.rootfs, 'UUID')
            with open(f"{MOUNT_POINT}/etc/fstab", "w") as f:
                f.write(f"UUID={root_uuid} / ext4 defaults 0 1\n")
                if self.args.boot:
                    boot_uuid = get_blk_value(self.args.boot, 'UUID')
                    fs_type = "vfat" if self.uefi else "ext4"
                    mount = '/boot/efi' if self.uefi else '/boot'
                    f.write(f"UUID={boot_uuid} {mount} {fs_type} defaults 0 2\n")

    def install_bootloader(self):
        log("Installing Bootloader (GRUB)...", "info")
        
        # Configure /etc/default/grub
        grub_path = f"{MOUNT_POINT}/etc/default/grub"
        if os.path.exists(grub_path):
            try:
                with open(grub_path, 'r') as f: lines = f.readlines()
                with open(grub_path, 'w') as f:
                    for line in lines:
                        if line.strip().startswith("GRUB_DISTRIBUTOR="):
                            f.write("GRUB_DISTRIBUTOR='AnOS'\n")
                        elif line.strip().startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                            new_line = line.replace("quiet", "").replace("  ", " ").strip()
                            if new_line.endswith('"'): new_line = new_line[:-1]
                            
                            # Nếu có NVIDIA: Ép dùng Proprietary driver, tắt Nouveau
                            if getattr(self, 'has_nvidia', False):
                                new_line += " nvidia_drm.modeset=1 nouveau.modeset=0\""
                            else:
                                new_line += " quiet\""
                                
                            f.write(new_line + "\n")
                        else:
                            f.write(line)
            except Exception as e:
                log(f"Failed to edit grub config: {e}", "warn")

        target = "x86_64-efi" if self.uefi else "i386-pc"
        boot_id = "AnOS"

        cmd =["grub-install", f"--target={target}", f"--bootloader-id={boot_id}", "--recheck"]
        if self.uefi: 
            cmd.append("--efi-directory=/boot/efi")
        else: 
            cmd.append(self.disk)
        
        run_cmd(cmd, chroot=True, stream=True)
        run_cmd("grub-mkconfig -o /boot/grub/grub.cfg", chroot=True, stream=True)

    def run_custom_scripts(self):
        if not self.args.run: return
        log(f"Running Post-Install Command: {self.args.run}", "warn")
        run_cmd(self.args.run, chroot=True, stream=True)

    def finalize(self):
        run_cmd("systemd-machine-id-setup", chroot=True, ignore_error=True)

    def cleanup(self):
        log("Cleaning up mounts...", "info")
        run_cmd(["umount", "-R", MOUNT_POINT], check=False, ignore_error=True)

# --- Entry Point ---
def main():
    parser = argparse.ArgumentParser()
    
    # Disk Setup Arguments
    parser.add_argument("--disk", help="Full Disk Wipe Mode (e.g., /dev/sda)")
    parser.add_argument("--shrink-part", help="Dual Boot: Partition Windows muốn cắt (e.g., /dev/nvme0n1p3)")
    parser.add_argument("--anos-size", help="Dual Boot: Dung lượng (GB) lấy ra để cài AnOS")
    parser.add_argument("--boot", help="Manual: Boot partition")
    parser.add_argument("--rootfs", help="Manual: Root partition")
    parser.add_argument("--swap", help="Manual: Swap partition")
    
    # AnOS Configuration Arguments
    parser.add_argument("--target", default="anos", choices=["anos"])
    parser.add_argument("--profiles", default="minimal", help="Comma-separated profiles: minimal,office,gaming,dev")
    parser.add_argument("--packages", help="Comma-separated list các packages để cài đặt lúc chroot (truyền từ GUI)")
    
    # User & System
    parser.add_argument("--user", help="Create a new user")
    parser.add_argument("--passwd", help="Password for the new user AND root")
    parser.add_argument("--host", default="AnOS", help="Computer Name (Hostname)")
    parser.add_argument("--timezone", default="Asia/Ho_Chi_Minh", help="Set Timezone (e.g. Asia/Ho_Chi_Minh)")
    
    parser.add_argument("--run", help="Custom command to run inside chroot after install")
    parser.add_argument("--debug", action="store_true", help="Enable verbose output")
    parser.add_argument("--i-am-very-stupid", action="store_true", help="Bypass safety warning prompt")
    
    args = parser.parse_args()
    
    global DEBUG_MODE
    DEBUG_MODE = args.debug

    if os.geteuid() != 0: 
        sys.exit("Run as root.")
        
    if not args.disk and not args.shrink_part and not (args.boot and args.rootfs):
        sys.exit("Error: Phải chỉ định `--disk` HOẶC (`--shrink-part` + `--anos-size`) HOẶC (`--boot` + `--rootfs`)")

    if args.shrink_part and not args.anos_size:
        sys.exit("Error: Chế độ Dual Boot cần cung cấp `--anos-size` (GB)")

    AnOSInstaller(args).run()

if __name__ == "__main__":
    main()
