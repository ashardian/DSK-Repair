# 🚀 DSK Repair – Intelligent Disk Repair Utility

**Author:** Ashar Dian  

DSK Repair is an advanced disk inspection and repair utility for Linux.  
It provides both an **interactive menu** and **command-line (CLI) one-shot options**, combining safe diagnostics, conservative repair flows, and optional integration with `ddrescue` for disk imaging.

---

## ✨ Features

- **Interactive Menu + CLI**: Choose between a guided menu or one-shot command-line flags.
- **Automatic Partition Detection**: Unmounted partitions are identified on startup.
- **Safe Repair Workflow**: Conservative first, prompts before destructive actions.
- **Filesystem Support**:
  - `ext2`, `ext3`, `ext4`
  - `ntfs` (via `ntfsfix`, `ntfs-3g`)
  - `exfat` / `vfat`
- **Disk Imaging**: Integration with `ddrescue` for safe disk imaging and recovery.
- **Diagnostics**:
  - `lsblk` partition/device listings
  - Filesystem type detection (`blkid`)
  - `dmesg` log inspection
  - SMART health checks (`smartctl`)
- **Colored Badges (optional)**: ✅ Success, ❌ Error, ⚠️ Warning, ℹ️ Info (via `colorama`).
- **Logging**: Writes activity logs to `/var/log/dsk_repair.log`.

---

# 🔧 Installation

1. Ensure Python 3.7+ is installed.
2. Install optional dependencies:
   ```bash
   sudo apt install smartmontools ntfs-3g gddrescue exfat-fuse exfat-utils dosfstools e2fsprogs


3. (Optional) Install `colorama` for colored output:

   ```bash
   pip install colorama
   ```
4. Clone or copy this repository:

   ```bash
   git clone https://github.com/ashardian/DSK-Repair.git
   cd DSK-repair
   ```
5. Make the script executable:

   ```bash
   chmod +x disk_repair_tool.py
   ```

---

## 🚀 Usage

### Interactive Menu

Simply run without arguments:

```bash
sudo ./disk_repair_tool.py
```

You’ll be presented with an interactive menu:

```
=== DSK Repair Menu ===
1) List all block devices
2) List drives (whole disks)
3) Inspect a partition
4) Repair a partition
5) Repair and Mount a partition
6) Create disk image with ddrescue
7) Mount a partition manually
8) Exit
```

---

### CLI Options (One-Shot Mode)

Run with arguments for direct execution:

```bash
sudo ./disk_repair_tool.py [OPTIONS]
```

**Available options:**

| Option             | Description                                       |
| ------------------ | ------------------------------------------------- |
| `--version`        | Show tool version                                 |
| `--list`           | List all block devices                            |
| `--drives`         | List only whole drives                            |
| `--inspect PART`   | Inspect a partition (e.g., `/dev/sdb2`)           |
| `--repair PART`    | Repair a partition (requires root)                |
| `--image SRC DEST` | Create an image of SRC to DEST with `ddrescue`    |
| `--mapfile FILE`   | Mapfile for ddrescue (default: DEST.map)          |
| `--yes`            | Assume "yes" for repair prompts (non-interactive) |

---

### Example Commands

* **List all partitions:**

  ```bash
  ./disk_repair_tool.py --list
  ```

* **Inspect a partition:**

  ```bash
  ./disk_repair_tool.py --inspect /dev/sdb1
  ```

* **Repair an ext4 partition (interactive prompts):**

  ```bash
  sudo ./disk_repair_tool.py --repair /dev/sdb2
  ```

* **Repair with auto-confirmation:**

  ```bash
  sudo ./disk_repair_tool.py --repair /dev/sdb2 --yes
  ```

* **Create a disk image with ddrescue:**

  ```bash
  sudo ./disk_repair_tool.py --image /dev/sdb /mnt/backup/sdb.img --mapfile /mnt/backup/sdb.map
  ```

---

## ⚠️ Safety Notes

* **Run as root**: Most operations (repair, mount, imaging) require `sudo`.
* **Read-only first**: The tool attempts non-destructive checks before repairs.
* **Backup critical data**: Always image a failing drive (`ddrescue`) before attempting repairs.
* **Windows NTFS caution**: After `ntfsfix`, run `chkdsk /f /r` in Windows for full repairs.

---

## 📝 Logging

All operations are logged to:

```
/var/log/dsk_repair.log
```


## 📜 License

This tool is provided as-is for educational and recovery purposes.
Use at your own risk. Ensure backups before performing repairs.

---
