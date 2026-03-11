#!/usr/bin/env python3
import sys
import os
import subprocess
import json
import shutil
import socket
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QStackedWidget, QPushButton,
                               QRadioButton, QComboBox, QLineEdit, QCheckBox,
                               QFrame, QListWidget, QListWidgetItem, QMessageBox,
                               QTextEdit, QProgressBar, QSpinBox, QGroupBox,
                               QDialog, QToolButton)
from PySide6.QtCore import Qt, QProcess, QTimer
from PySide6.QtGui import QPixmap, QIcon, QFont, QTextCursor

# --- Configuration & Constants ---
ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_LOGO_PATH = os.path.join(ASSET_DIR, "logo.png")
BG_PATH = os.path.join(ASSET_DIR, "/usr/share/pixmaps/backg.png")
BACKEND_SCRIPT = "./chimera.py" 
ZONEINFO_PATH = "/usr/share/zoneinfo"

# Danh sách Packages theo Profile
PKG_MAP = {
    # Minimal / Base (Luôn có)
    "google-chrome": "minimal",
    "sudo-gui": "minimal",
    "freetube-bin": "minimal",
    "harmonymusic": "minimal",
    # Office
    "libreoffice-fresh": "office",
    # Gaming
    "wine": "gaming",
    "gamemode": "gaming",
    "mangohud": "gaming",
    "steam": "gaming",
    # Dev
    "neovim": "dev",
    "vim": "dev",
    "python": "dev",
    "git": "dev",
    "gcc": "dev",
    "clang": "dev",
    "rustup": "dev",
    "flutter-bin": "dev",
    "android-studio": "dev",
    "visual-studio-code-bin": "dev"
}

# --- Utility Functions ---
def get_os_release():
    info = {
        "NAME": "AnOS",
        "PRETTY_NAME": "AnOS",
        "LOGO": "anos"
    }
    try:
        os_release_path = "/etc/os_release" if not os.path.exists("/etc/os-release") else "/etc/os-release"
        if os.path.exists(os_release_path):
            with open(os_release_path) as f:
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        info[k] = v.strip('"').strip("'")
    except Exception:
        pass
    return info

# --- Custom Widgets ---
class StepItem(QListWidgetItem):
    def __init__(self, text):
        super().__init__(text)
        self.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        font = QFont()
        font.setPointSize(11)
        self.setFont(font)

class DebugDialog(QDialog):
    def __init__(self, parent=None, command="", dry_run=False):
        super().__init__(parent)
        self.setWindowTitle("Installer Settings (Debug)")
        self.resize(600, 400)
        
        layout = QVBoxLayout(self)
        self.chk_dry_run = QCheckBox("Enable Dry Run (Do not write to disk)")
        self.chk_dry_run.setChecked(dry_run)
        layout.addWidget(self.chk_dry_run)
        
        layout.addWidget(QLabel("Generated Backend Command:"))
        self.txt_cmd = QTextEdit()
        self.txt_cmd.setPlainText(command)
        self.txt_cmd.setReadOnly(True)
        layout.addWidget(self.txt_cmd)
        
        btn_close = QPushButton("Apply & Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

# --- Main Window ---
class InstallerWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.os_info = get_os_release()
        self.distro_name = "AnOS"
        self.setWindowTitle(f"{self.distro_name} Installer")
        self.resize(1000, 700)

        self.dry_run = False
        self.is_online = self.check_internet()
        
        self.install_data = {
            "install_type": "online" if self.is_online else "offline",
            "disk": None, "root": None, "boot": None, "swap": None,
            "method": "whole", "shrink_part": None, "anos_size": 0,
            "user": "", "pass": "", "host": "anos-pc", "tz": "Asia/Ho_Chi_Minh",
            "keyboard": "us", "profiles": ["minimal"], "packages":[]
        }

        self.setup_ui()
        self.check_root()

    def check_root(self):
        if os.geteuid() != 0:
            QMessageBox.warning(self, "Root Required", "Running without root privileges.\nDisk operations will fail.")

    def check_internet(self):
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=3)
            return True
        except OSError:
            pass
        return False

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Sidebar ---
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(240)
        self.sidebar.setFrameShape(QFrame.StyledPanel)
        
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(0, 0, 0, 15)
        side_layout.setSpacing(10)

        lbl_logo = QLabel()
        lbl_logo.setAlignment(Qt.AlignCenter)
        lbl_logo.setFixedHeight(140)

        if os.path.exists(LOCAL_LOGO_PATH):
            pix = QPixmap(LOCAL_LOGO_PATH).scaled(110, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl_logo.setPixmap(pix)
        else:
            lbl_logo.setText(self.distro_name)
            font = QFont()
            font.setBold(True)
            font.setPointSize(20)
            lbl_logo.setFont(font)

        side_layout.addWidget(lbl_logo)

        self.step_list = QListWidget()
        self.step_list.setFocusPolicy(Qt.NoFocus)
        steps =["Welcome", "Location & KB", "Profile", "Disk Setup", "Partitions", "Users", "Summary", "Install"]
        for s in steps: self.step_list.addItem(StepItem(s))
        self.step_list.setCurrentRow(0)
        side_layout.addWidget(self.step_list)

        self.btn_debug = QToolButton()
        self.btn_debug.setText("⚙")
        self.btn_debug.setCursor(Qt.PointingHandCursor)
        self.btn_debug.clicked.connect(self.open_debug_settings)
        self.btn_debug.setFixedSize(40, 40)

        bot_layout = QHBoxLayout()
        bot_layout.setContentsMargins(15, 0, 0, 0)
        bot_layout.addWidget(self.btn_debug)
        bot_layout.addStretch()
        side_layout.addLayout(bot_layout)
        main_layout.addWidget(self.sidebar)

        # --- Content ---
        self.content_container = QWidget()
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(40, 40, 40, 40)

        self.lbl_header = QLabel(f"Welcome to {self.distro_name}")
        header_font = QFont()
        header_font.setPointSize(20)
        header_font.setBold(True)
        self.lbl_header.setFont(header_font)
        content_layout.addWidget(self.lbl_header)

        self.pages = QStackedWidget()
        content_layout.addWidget(self.pages)

        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(0, 20, 0, 0)
        self.btn_back = QPushButton("Back")
        self.btn_next = QPushButton("Next")
        self.btn_back.clicked.connect(self.go_back)
        self.btn_next.clicked.connect(self.go_next)

        nav_layout.addStretch()
        nav_layout.addWidget(self.btn_back)
        nav_layout.addWidget(self.btn_next)
        content_layout.addLayout(nav_layout)
        main_layout.addWidget(self.content_container)

        self.init_pages()
        self.update_nav()

    def init_pages(self):
        # 0. Welcome
        p_welcome = QWidget()
        vbox = QVBoxLayout(p_welcome)
        lbl_hero = QLabel()
        lbl_hero.setAlignment(Qt.AlignCenter)
        if os.path.exists(BG_PATH):
            pix = QPixmap(BG_PATH).scaled(700, 350, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl_hero.setPixmap(pix)
        else:
            lbl_hero.setText(f"{self.distro_name}\nInstaller")
            lbl_hero.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
            lbl_hero.setFixedSize(700, 350)

        net_status = "<span style='color:green;'>Online</span>" if self.is_online else "<span style='color:red;'>Offline (Fallback Mode)</span>"
        welcome_str = f"<h3>Triết lý: Dễ dùng, Dễ hiểu</h3>Network Status: <b>{net_status}</b><br><br>Chào mừng bạn đến với trình cài đặt AnOS."
        lbl_text = QLabel(welcome_str)
        lbl_text.setAlignment(Qt.AlignCenter)
        lbl_text.setWordWrap(True)
        lbl_text.setContentsMargins(0, 20, 0, 0)
        
        vbox.addStretch()
        vbox.addWidget(lbl_hero)
        vbox.addWidget(lbl_text)
        vbox.addStretch()
        self.pages.addWidget(p_welcome)

        # 1. Location & Keyboard
        p_loc = QWidget()
        vbox = QVBoxLayout(p_loc)

        vbox.addWidget(QLabel("<b>Select Region:</b>"))
        self.cmb_region = QComboBox()
        self.cmb_region.currentTextChanged.connect(self.populate_cities)
        vbox.addWidget(self.cmb_region)

        vbox.addWidget(QLabel("<b>Select Zone/City:</b>"))
        self.cmb_city = QComboBox()
        vbox.addWidget(self.cmb_city)
        self.populate_regions()

        vbox.addWidget(QLabel("<b>Keyboard Layout:</b>"))
        self.cmb_kbd = QComboBox()
        self.cmb_kbd.addItems(["us", "uk", "fr", "de", "vn", "es"])
        vbox.addWidget(self.cmb_kbd)

        vbox.addStretch()
        self.pages.addWidget(p_loc)

        # 2. Profile Selection
        p_prof = QWidget()
        vbox = QVBoxLayout(p_prof)
        vbox.addWidget(QLabel("<b>Chọn Profile (Mục đích sử dụng):</b>\n*Minimal mặc định luôn được chọn."))
        
        hbox = QHBoxLayout()
        self.chk_office = QCheckBox("Office (Văn phòng)")
        self.chk_gaming = QCheckBox("Gaming (Chơi game)")
        self.chk_dev = QCheckBox("Dev (Lập trình)")
        
        self.chk_office.toggled.connect(self.update_package_list)
        self.chk_gaming.toggled.connect(self.update_package_list)
        self.chk_dev.toggled.connect(self.update_package_list)

        hbox.addWidget(self.chk_office)
        hbox.addWidget(self.chk_gaming)
        hbox.addWidget(self.chk_dev)
        vbox.addLayout(hbox)

        vbox.addWidget(QLabel("<b>Tùy chỉnh Packages:</b>"))
        self.lst_packages = QListWidget()
        for pkg, prof in PKG_MAP.items():
            item = QListWidgetItem(f"{pkg} ({prof})")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            # Default check minimal
            if prof == "minimal":
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, pkg)
            item.setData(Qt.UserRole + 1, prof)
            self.lst_packages.addItem(item)

        vbox.addWidget(self.lst_packages)
        if not self.is_online:
            vbox.addWidget(QLabel("<span style='color:red;'>*Offline: Các packages sẽ được ghi nhận và cài đặt sau bởi Welcome App khi có mạng.</span>"))
            
        self.pages.addWidget(p_prof)

        # 3. Disk Setup
        p_disk = QWidget()
        vbox = QVBoxLayout(p_disk)

        grp = QGroupBox("Thiết lập Ổ đĩa (Setup Disk)")
        gv = QVBoxLayout()
        
        self.rad_whole = QRadioButton("Choose full disk (Sử dụng toàn bộ ổ cứng)")
        self.rad_dual = QRadioButton("Dual boot setup (Cài song song với Windows hiện tại)")
        self.rad_manual = QRadioButton("Manual partition (Dành cho Advance User)")
        self.rad_whole.setChecked(True)
        
        self.rad_whole.toggled.connect(self.toggle_disk_ui)
        self.rad_dual.toggled.connect(self.toggle_disk_ui)
        self.rad_manual.toggled.connect(self.toggle_disk_ui)
        
        gv.addWidget(self.rad_whole)
        gv.addWidget(self.rad_dual)
        gv.addWidget(self.rad_manual)
        grp.setLayout(gv)
        vbox.addWidget(grp)

        # Widget cho Whole Disk
        self.wid_whole = QWidget()
        v_whole = QVBoxLayout(self.wid_whole)
        v_whole.setContentsMargins(0,0,0,0)
        v_whole.addWidget(QLabel("<b>Select Storage Drive to Wipe:</b>"))
        self.cmb_disk = QComboBox()
        v_whole.addWidget(self.cmb_disk)
        warn_lbl = QLabel("<span style='color:red;'>⚠️ CẢNH BÁO ĐỎ: Sẽ FORMAT và BAY MÀU TOÀN BỘ dữ liệu trên ổ đĩa!</span>")
        v_whole.addWidget(warn_lbl)
        vbox.addWidget(self.wid_whole)

        # Widget cho Dual Boot
        self.wid_dual = QWidget()
        v_dual = QVBoxLayout(self.wid_dual)
        v_dual.setContentsMargins(0,0,0,0)
        v_dual.addWidget(QLabel("<b>Chọn ổ đĩa chứa Windows (NTFS) để thu nhỏ:</b>"))
        self.cmb_ntfs = QComboBox()
        v_dual.addWidget(self.cmb_ntfs)
        
        h_spin = QHBoxLayout()
        h_spin.addWidget(QLabel("Dung lượng cắt ra cho AnOS (GB):"))
        self.spin_anos_size = QSpinBox()
        self.spin_anos_size.setRange(20, 2000) # Min 20GB cho AnOS
        self.spin_anos_size.setValue(40)
        h_spin.addWidget(self.spin_anos_size)
        v_dual.addLayout(h_spin)
        self.wid_dual.setVisible(False)
        vbox.addWidget(self.wid_dual)

        self.refresh_disks()
        vbox.addStretch()
        self.pages.addWidget(p_disk)

        # 4. Partitions (Manual Only)
        p_part = QWidget()
        vbox = QVBoxLayout(p_part)
        info = QLabel("<b>Partition Manager</b><br>Dùng cfdisk chia ổ đĩa, sau đó Refresh và chọn Mount point.")
        vbox.addWidget(info)
        btn_cfdisk = QPushButton(" Mở GParted / cfdisk")
        btn_cfdisk.setIcon(QIcon.fromTheme("utilities-terminal"))
        btn_cfdisk.clicked.connect(self.launch_cfdisk)
        vbox.addWidget(btn_cfdisk)

        part_grid = QGroupBox("Mount Point Assignment")
        pg_layout = QVBoxLayout(part_grid)
        pg_layout.addWidget(QLabel("Root Partition (/):"))
        self.cmb_root = QComboBox()
        pg_layout.addWidget(self.cmb_root)
        pg_layout.addWidget(QLabel("Boot Partition (/boot or EFI):"))
        self.cmb_boot = QComboBox()
        pg_layout.addWidget(self.cmb_boot)
        pg_layout.addWidget(QLabel("Swap Partition (Tùy chọn):"))
        self.cmb_swap = QComboBox()
        pg_layout.addWidget(self.cmb_swap)
        btn_refresh = QPushButton("Làm mới danh sách phân vùng")
        btn_refresh.clicked.connect(self.populate_partitions)
        pg_layout.addWidget(btn_refresh)
        vbox.addWidget(part_grid)
        vbox.addStretch()
        self.pages.addWidget(p_part)

        # 5. Users
        p_user = QWidget()
        form = QVBoxLayout(p_user)
        self.inp_host = QLineEdit("anos-pc")
        self.inp_user = QLineEdit()
        self.inp_pass = QLineEdit()
        self.inp_pass.setEchoMode(QLineEdit.Password)
        form.addWidget(QLabel("Computer Name (Hostname):"))
        form.addWidget(self.inp_host)
        form.addWidget(QLabel("Username:"))
        form.addWidget(self.inp_user)
        form.addWidget(QLabel("Password (Dùng chung cho Root & User):"))
        form.addWidget(self.inp_pass)
        form.addStretch()
        self.pages.addWidget(p_user)

        # 6. Summary
        p_sum = QWidget()
        vbox = QVBoxLayout(p_sum)
        self.txt_sum = QTextEdit()
        self.txt_sum.setReadOnly(True)
        vbox.addWidget(QLabel("Installation Summary:"))
        vbox.addWidget(self.txt_sum)
        self.pages.addWidget(p_sum)

        # 7. Install
        p_inst = QWidget()
        vbox = QVBoxLayout(p_inst)
        self.lbl_progress = QLabel("Waiting to start...")
        self.lbl_progress.setAlignment(Qt.AlignCenter)
        self.pbar = QProgressBar()
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        font_mono = QFont("Monospace")
        font_mono.setStyleHint(QFont.Monospace)
        self.txt_log.setFont(font_mono)
        
        vbox.addStretch()
        vbox.addWidget(self.lbl_progress)
        vbox.addWidget(self.pbar)
        vbox.addWidget(self.txt_log)
        vbox.addStretch()
        self.pages.addWidget(p_inst)

    def toggle_disk_ui(self):
        self.wid_whole.setVisible(self.rad_whole.isChecked())
        self.wid_dual.setVisible(self.rad_dual.isChecked())

    def update_package_list(self):
        active_profiles = ["minimal"]
        if self.chk_office.isChecked(): active_profiles.append("office")
        if self.chk_gaming.isChecked(): active_profiles.append("gaming")
        if self.chk_dev.isChecked(): active_profiles.append("dev")

        for i in range(self.lst_packages.count()):
            item = self.lst_packages.item(i)
            prof = item.data(Qt.UserRole + 1)
            if prof in active_profiles:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)

    # --- Timezone Logic ---
    def populate_regions(self):
        self.cmb_region.blockSignals(True)
        self.cmb_region.clear()

        if not os.path.exists(ZONEINFO_PATH):
            self.cmb_region.addItem("UTC")
            return

        regions =[]
        has_global_files = False

        for entry in os.listdir(ZONEINFO_PATH):
            full_path = os.path.join(ZONEINFO_PATH, entry)
            if os.path.isdir(full_path):
                if entry not in["posix", "right", "SystemV", "Etc", "posixrules"]:
                    regions.append(entry)
            elif os.path.isfile(full_path) and entry[0].isupper() and not entry.endswith(".tab"):
                has_global_files = True

        regions.sort()
        if has_global_files:
            regions.insert(0, "Global")

        self.cmb_region.addItems(regions)
        self.cmb_region.blockSignals(False)

        # Try to auto set Asia/Ho_Chi_Minh for AnOS default
        idx = self.cmb_region.findText("Asia")
        if idx >= 0:
            self.cmb_region.setCurrentIndex(idx)
            self.populate_cities("Asia")
            idx_c = self.cmb_city.findData("Asia/Ho_Chi_Minh")
            if idx_c >= 0: self.cmb_city.setCurrentIndex(idx_c)

    def populate_cities(self, region):
        self.cmb_city.clear()
        if region == "Global":
            for entry in sorted(os.listdir(ZONEINFO_PATH)):
                full = os.path.join(ZONEINFO_PATH, entry)
                if os.path.isfile(full) and entry[0].isupper() and not entry.endswith(".tab"):
                    self.cmb_city.addItem(entry, entry)
        else:
            base_path = os.path.join(ZONEINFO_PATH, region)
            if not os.path.exists(base_path): return

            zones =[]
            for root, dirs, files in os.walk(base_path):
                for f in files:
                    if f.startswith(".") or f.endswith(".tab"): continue
                    abs_path = os.path.join(root, f)
                    rel_display = os.path.relpath(abs_path, base_path)
                    full_tz = f"{region}/{rel_display}"
                    zones.append((rel_display, full_tz))

            zones.sort(key=lambda x: x[0])
            for display, data in zones:
                self.cmb_city.addItem(display, data)

    def refresh_disks(self):
        self.cmb_disk.clear()
        self.cmb_ntfs.clear()
        try:
            # Load full disks
            out = subprocess.check_output(["lsblk", "-d", "-n", "-o", "NAME,SIZE,MODEL,TYPE", "-J"]).decode()
            data = json.loads(out)
            for d in data.get('blockdevices', []):
                if d['type'] in['loop', 'rom'] or d['name'].startswith('zram'): continue
                model = d.get('model', 'Unknown Drive') or "Unknown Drive"
                self.cmb_disk.addItem(f"{model} ({d['size']}) - /dev/{d['name']}", f"/dev/{d['name']}")
                
            # Load NTFS partitions for dual boot
            out2 = subprocess.check_output(["lsblk", "-l", "-n", "-o", "NAME,SIZE,FSTYPE,TYPE", "-J"]).decode()
            data2 = json.loads(out2)
            for dev in data2.get('blockdevices',[]):
                if dev['type'] == 'part' and str(dev.get('fstype')).lower() == 'ntfs':
                    self.cmb_ntfs.addItem(f"/dev/{dev['name']} ({dev['size']})", f"/dev/{dev['name']}")
        except Exception as e: 
            self.cmb_disk.addItem(f"Error: {e}", None)

    def launch_cfdisk(self):
        terms =["gparted", "konsole", "xterm", "gnome-terminal", "alacritty"]
        term_cmd = None
        for t in terms:
            if shutil.which(t):
                if t == "gparted": term_cmd = [t]
                elif t == "konsole": term_cmd = [t, "--hide-menubar", "-e", "cfdisk"]
                else: term_cmd = [t, "-e", "cfdisk"]
                break
        if term_cmd:
            subprocess.run(term_cmd)
            self.populate_partitions()

    def populate_partitions(self):
        self.cmb_root.clear()
        self.cmb_boot.clear()
        self.cmb_swap.clear()
        self.cmb_swap.addItem("None", None)
        try:
            cmd =["lsblk", "-l", "-n", "-o", "NAME,SIZE,FSTYPE,TYPE", "-J"]
            out = subprocess.check_output(cmd).decode()
            data = json.loads(out)
            for dev in data.get('blockdevices', []):
                if dev['type'] == 'part':
                    fstype = dev.get('fstype') or "Unformatted"
                    txt = f"/dev/{dev['name']} ({dev['size']}) - {fstype}"
                    val = f"/dev/{dev['name']}"
                    self.cmb_root.addItem(txt, val)
                    self.cmb_boot.addItem(txt, val)
                    self.cmb_swap.addItem(txt, val)
        except Exception: pass

    def get_cmd_list(self):
        cmd = ["python3", "-u", BACKEND_SCRIPT, "--target", "anos"]
        d = self.install_data

        # Disk Configuration
        if d['method'] == 'whole':
            if d['disk']: cmd.extend(["--disk", d['disk']])
        elif d['method'] == 'dual':
            if d['shrink_part']:
                cmd.extend(["--shrink-part", d['shrink_part']])
                cmd.extend(["--anos-size", str(d['anos_size'])])
        else:
            if d['root']: cmd.extend(["--rootfs", d['root']])
            if d['boot']: cmd.extend(["--boot", d['boot']])
            if d['swap']: cmd.extend(["--swap", d['swap']])

        # Profiles & Packages
        profiles = ",".join(d['profiles'])
        cmd.extend(["--profiles", profiles])
        if d['packages']:
            pkgs = ",".join(d['packages'])
            cmd.extend(["--packages", pkgs])

        # Users & System
        cmd.extend(["--user", d['user']])
        cmd.extend(["--passwd", d['pass']])
        cmd.extend(["--host", d['host']])
        cmd.extend(["--timezone", d['tz']])
        
        # We don't need --online flag in AnOS because logic auto detects in backend,
        # but you can add it if needed. AnOS treemap relies on check_connection in chimera.py.
        cmd.append("--i-am-very-stupid")
        cmd.append("--debug")
        return cmd

    def open_debug_settings(self):
        dlg = DebugDialog(self, " ".join(self.get_cmd_list()), self.dry_run)
        if dlg.exec():
            self.dry_run = dlg.chk_dry_run.isChecked()

    def go_next(self):
        idx = self.pages.currentIndex()

        # Page 1: Location & KB
        if idx == 1:
            self.install_data['tz'] = self.cmb_city.currentData()
            self.install_data['keyboard'] = self.cmb_kbd.currentText()

        # Page 2: Profile & Packages
        if idx == 2:
            profs = ["minimal"]
            if self.chk_office.isChecked(): profs.append("office")
            if self.chk_gaming.isChecked(): profs.append("gaming")
            if self.chk_dev.isChecked(): profs.append("dev")
            self.install_data['profiles'] = profs

            pkgs =[]
            for i in range(self.lst_packages.count()):
                item = self.lst_packages.item(i)
                if item.checkState() == Qt.Checked:
                    pkgs.append(item.data(Qt.UserRole))
            self.install_data['packages'] = pkgs

        # Page 3: Setup Disk
        if idx == 3:
            if self.rad_whole.isChecked():
                self.install_data['method'] = "whole"
                self.install_data['disk'] = self.cmb_disk.currentData()
                if not self.install_data['disk']: return QMessageBox.warning(self, "Error", "Hãy chọn ổ đĩa.")
                self.pages.setCurrentIndex(5) # Skip Partitions
                self.step_list.setCurrentRow(5)
                self.update_nav()
                return
            elif self.rad_dual.isChecked():
                self.install_data['method'] = "dual"
                self.install_data['shrink_part'] = self.cmb_ntfs.currentData()
                self.install_data['anos_size'] = self.spin_anos_size.value()
                if not self.install_data['shrink_part']: return QMessageBox.warning(self, "Error", "Không tìm thấy phân vùng Windows (NTFS).")
                self.pages.setCurrentIndex(5) # Skip Partitions
                self.step_list.setCurrentRow(5)
                self.update_nav()
                return
            else:
                self.install_data['method'] = "manual"
                self.populate_partitions()

        # Page 4: Partitions
        if idx == 4:
            r, b = self.cmb_root.currentData(), self.cmb_boot.currentData()
            if not r or not b: return QMessageBox.warning(self, "Error", "Yêu cầu Mount Root (/) và Boot.")
            self.install_data['root'] = r
            self.install_data['boot'] = b
            self.install_data['swap'] = self.cmb_swap.currentData()

        # Page 5: Users
        if idx == 5:
            u, p = self.inp_user.text(), self.inp_pass.text()
            if not u or not p: return QMessageBox.warning(self, "Error", "User và Password là bắt buộc.")
            self.install_data['user'] = u
            self.install_data['pass'] = p
            self.install_data['host'] = self.inp_host.text()
            self.generate_summary()

        # Page 6: Summary -> Install
        if idx == 6:
            if not self.dry_run:
                if QMessageBox.question(self, "Confirm", "Disk changes are permanent. Proceed?", QMessageBox.Yes|QMessageBox.No) != QMessageBox.Yes: return
            self.start_install()
            return

        if idx < self.pages.count() - 1:
            self.pages.setCurrentIndex(idx + 1)
            self.step_list.setCurrentRow(idx + 1)

        self.update_nav()

    def go_back(self):
        idx = self.pages.currentIndex()
        if idx == 5 and self.install_data['method'] in ['whole', 'dual']:
            self.pages.setCurrentIndex(3)
            self.step_list.setCurrentRow(3)
        elif idx > 0:
            self.pages.setCurrentIndex(idx - 1)
            self.step_list.setCurrentRow(idx - 1)
        self.update_nav()

    def update_nav(self):
        idx = self.pages.currentIndex()
        if idx < self.step_list.count():
             self.step_list.setCurrentRow(idx)
             self.lbl_header.setText(self.step_list.item(idx).text())

        self.btn_back.setVisible(idx > 0 and idx < 7)
        self.btn_next.setVisible(idx < 7)

        if idx == 6:
            self.btn_next.setText("Bắt đầu cài đặt")
        else:
            self.btn_next.setText("Next")

    def generate_summary(self):
        d = self.install_data
        html = f"""
        <h3>System Configuration</h3>
        <b>Hostname:</b> {d['host']}<br><b>User:</b> {d['user']}<br>
        <b>Timezone:</b> {d['tz']} (KB: {d['keyboard']})<br>
        <b>Profiles:</b> {", ".join(d['profiles']).upper()}<br>
        <b>Packages To Install:</b> {len(d['packages'])} gói<br>
        <h3>Storage Configuration</h3>
        """
        if d['method'] == 'whole': 
            html += f"<b>Mode:</b> Erase Whole Disk<br><b>Target:</b> {d['disk']}<br><b>Swap:</b> Tự động (RAM/2)"
        elif d['method'] == 'dual':
            html += f"<b>Mode:</b> Dual Boot (Shrink Windows)<br><b>Shrink Target:</b> {d['shrink_part']}<br><b>AnOS Size:</b> {d['anos_size']} GB"
        else: 
            html += f"<b>Mode:</b> Manual Partitioning<br><b>Root:</b> {d['root']}<br><b>Boot:</b> {d['boot']}<br><b>Swap:</b> {d['swap']}"
        self.txt_sum.setHtml(html)

    def start_install(self):
        self.pages.setCurrentIndex(7)
        self.step_list.setCurrentRow(7)
        self.update_nav()
        cmd = self.get_cmd_list()

        if self.dry_run:
            self.txt_log.append("--- DRY RUN MODE ---")
            self.txt_log.append(f"Command:\n{' '.join(cmd)}")
            self.pbar.setValue(100)
            self.lbl_progress.setText("Dry Run Complete")
            return

        self.process = QProcess()
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.install_finished)
        self.process.start(cmd[0], cmd[1:])
        self.pbar.setRange(0, 0)

    def read_output(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.txt_log.moveCursor(QTextCursor.End)
        self.txt_log.insertPlainText(data)
        self.txt_log.moveCursor(QTextCursor.End)
        lower = data.lower()
        if "partitioning" in lower or "wiping" in lower or "shrink" in lower: self.lbl_progress.setText("Partitioning Disk...")
        if "rsync" in lower or "clone" in lower: self.lbl_progress.setText("Copying Base System (AnOS)...")
        if "pacman" in lower or "packages" in lower: self.lbl_progress.setText("Installing Profiles & Packages...")
        if "nvidia" in lower: self.lbl_progress.setText("Setting up NVIDIA Mainline Driver...")
        if "bootloader" in lower or "grub" in lower: self.lbl_progress.setText("Installing Bootloader...")

    def install_finished(self):
        if self.process.exitCode() == 0:
            self.pbar.setRange(0, 100)
            self.pbar.setValue(100)
            self.lbl_progress.setText("Installation Successful!")
            QMessageBox.information(self, "Hoàn tất", "AnOS đã được cài đặt thành công! Vui lòng khởi động lại.")
        else:
            self.pbar.setRange(0, 100)
            self.pbar.setValue(0)
            self.lbl_progress.setText("Installation Failed")
            QMessageBox.critical(self, "Lỗi", "Quá trình cài đặt thất bại. Vui lòng kiểm tra log.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = InstallerWindow()
    win.show()
    sys.exit(app.exec())
