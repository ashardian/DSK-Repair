#!/usr/bin/env python3
"""
DSK Repair - Intelligent Disk Repair Utility (final script)

Features:
 - Interactive menu + one-shot CLI flags
 - Colored badges (✅, ❌, ⚠️, ℹ️) with colorama (optional)
 - Automatic detection of unmounted partitions at startup
 - Interactive selection of partitions by index
 - Conservative repair flows (safe first, confirm before destructive)
 - Supports ext2/3/4, ntfs, exfat/vfat
 - ddrescue integration for imaging
"""

from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

# -------------------- colors (optional) --------------------
try:
    from colorama import init as _c_init, Fore, Style
    _c_init(autoreset=True)
except Exception:
    # fallback: no colors
    class _NoColor:
        GREEN = ""
        RED = ""
        YELLOW = ""
        CYAN = ""
        MAGENTA = ""
        RESET = ""
    Fore = _NoColor()
    class _NoStyle:
        RESET_ALL = ""
    Style = _NoStyle()

# -------------------- config --------------------
VERSION = "2.3.0"
LOGFILE_DEFAULT = "/var/log/dsk_repair.log"

# -------------------- utilities --------------------
def run_text(cmd: List[str]) -> Tuple[int, str, str]:
    """Run command, return (rc, stdout, stderr) as strings."""
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return p.returncode, p.stdout or "", p.stderr or ""
    except FileNotFoundError as e:
        return 127, "", str(e)
    except Exception as e:
        return 1, "", str(e)

def which(program: str) -> Optional[str]:
    return shutil.which(program)

def safe_write_log(msg: str, logfile: str = LOGFILE_DEFAULT) -> None:
    try:
        # ensure directory exists
        logdir = os.path.dirname(logfile) or "/var/log"
        os.makedirs(logdir, exist_ok=True)
        with open(logfile, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass

def require_root() -> None:
    if os.geteuid() != 0:
        print(Fore.RED + "❌ Root required for this operation. Please re-run with sudo.")
        sys.exit(2)

def safe_str(x, default: str = "-") -> str:
    return default if x is None else str(x)

def banner() -> None:
    print(Fore.MAGENTA + "=" * 60)
    print(Fore.GREEN + "         🚀 DSK REPAIR 🚀")
    print(Fore.RED + "         Made by @Ashar Dian")
    print(Fore.CYAN + "   Intelligent Disk Utility for Linux")
    print(Fore.MAGENTA + "=" * 60)

def pretty_header(title: str) -> None:
    print(Fore.YELLOW + "\n" + "=" * 60)
    print(Fore.YELLOW + title)
    print(Fore.YELLOW + "=" * 60)

# -------------------- status badges --------------------
def badge_success(msg: str) -> str:
    return Fore.GREEN + "✅ " + msg + Fore.RESET

def badge_error(msg: str) -> str:
    return Fore.RED + "❌ " + msg + Fore.RESET

def badge_warn(msg: str) -> str:
    return Fore.YELLOW + "⚠️ " + msg + Fore.RESET

def badge_info(msg: str) -> str:
    return Fore.CYAN + "ℹ️ " + msg + Fore.RESET

# -------------------- discovery & printing --------------------
def list_block_devices() -> Dict:
    rc, out, err = run_text(["lsblk", "-J", "-o", "NAME,FSTYPE,SIZE,TYPE,MOUNTPOINT,LABEL,UUID,MODEL"])
    if rc != 0:
        raise RuntimeError(f"lsblk failed: {err.strip()}")
    return json.loads(out)

def print_block_devices(devs: Dict) -> None:
    pretty_header("Block Devices")
    for dev in devs.get("blockdevices", []):
        name = safe_str(dev.get("name"))
        dtype = safe_str(dev.get("type"))
        size = safe_str(dev.get("size"))
        model = safe_str(dev.get("model"))
        print(Fore.CYAN + f"/dev/{name:<12} {dtype:<6} SIZE:{size:<10} MODEL:{model}")
        for part in dev.get("children") or []:
            pname = safe_str(part.get("name"))
            pfs = safe_str(part.get("fstype"))
            psize = safe_str(part.get("size"))
            pmount = safe_str(part.get("mountpoint"))
            label = safe_str(part.get("label"))
            print("  " + Fore.GREEN + f"- /dev/{pname:<10} FS:{pfs:<8} SIZE:{psize:<10} MOUNT:{pmount:<15} LABEL:{label}")

def list_drives() -> None:
    devs = list_block_devices()
    pretty_header("Available Drives")
    found = False
    for dev in devs.get("blockdevices", []):
        if dev.get("type") == "disk":
            found = True
            name = safe_str(dev.get("name"))
            size = safe_str(dev.get("size"))
            model = safe_str(dev.get("model"))
            print(Fore.GREEN + f"/dev/{name:<12} SIZE:{size:<10} MODEL:{model}")
    if not found:
        print(Fore.YELLOW + "[!] No block disks found")

# -------------------- helpers --------------------
def is_block_device(path: str) -> bool:
    try:
        st = os.stat(path)
        return stat.S_ISBLK(st.st_mode)
    except Exception:
        return False

def validate_device_input(path: str) -> bool:
    return bool(path and path.startswith("/dev/") and os.path.exists(path) and is_block_device(path))

def get_parent_disk(partition: str) -> Optional[str]:
    if not partition.startswith("/dev/"):
        return None
    m = re.match(r"(.+?)(p?\d+)$", partition)
    return m.group(1) if m else None

def get_partition_info(dev: str) -> Dict:
    if not dev or not dev.startswith("/dev/"):
        return {"error": f"invalid device: {dev}"}
    rc, out, err = run_text(["blkid", dev])
    if rc != 0:
        return {"error": (err or out).strip()}
    parts = out.strip().split(":", 1)
    if len(parts) < 2:
        return {"raw": out.strip()}
    kv = {}
    for tok in parts[1].strip().split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            kv[k] = v.strip('"')
    return kv

def check_dmesg_for_device(device: str) -> str:
    devname = os.path.basename(device)
    rc, out, err = run_text(["dmesg"])
    text = (out or "") + "\n" + (err or "")
    lines = [l for l in text.splitlines() if devname in l]
    return "\n".join(lines[-200:]) if lines else ""

def smart_check(device: str) -> Dict:
    if not which("smartctl"):
        return {"error": "smartctl not installed"}
    results = {}
    for args in (["-H"], ["-i"]):
        cmd = ["smartctl"] + args + [device]
        rc, out, err = run_text(cmd)
        results[" ".join(args)] = {"rc": rc, "out": out.strip(), "err": err.strip()}
    return results

# -------------------- mount helpers --------------------
def create_mountpoint(base: str = "/mnt", name: Optional[str] = None) -> str:
    if not name:
        name = f"dskrepair_{int(time.time())}"
    mp = os.path.join(base, name)
    os.makedirs(mp, exist_ok=True)
    return mp

def attempt_mount(partition: str, mountpoint: str, fstype: Optional[str] = None, options: Optional[str] = None) -> Tuple[bool, str]:
    cmd = ["mount"]
    if fstype:
        cmd += ["-t", fstype]
    if options:
        cmd += ["-o", options]
    cmd += [partition, mountpoint]
    rc, out, err = run_text(cmd)
    return rc == 0, (out or "") + (err or "")

def mount_ntfs_with_ntfs3g(partition: str, mountpoint: str, options: Optional[str] = None) -> Tuple[bool, str]:
    if not which("ntfs-3g"):
        return False, "ntfs-3g not installed"
    cmd = ["ntfs-3g"]
    if options:
        cmd += ["-o", options]
    cmd += [partition, mountpoint]
    rc, out, err = run_text(cmd)
    return rc == 0, (out or "") + (err or "")

# -------------------- repair helpers --------------------
def repair_ntfs(partition: str, auto_yes: bool = False) -> Dict:
    if not which("ntfsfix"):
        return {"error": "ntfsfix not installed"}
    safe_write_log(f"ntfsfix start {partition}")
    rc, out, err = run_text(["ntfsfix", partition])
    return {"rc": rc, "out": out.strip(), "err": err.strip()}

def repair_extfs(partition: str, auto_yes: bool = False) -> Dict:
    if not which("e2fsck"):
        return {"error": "e2fsck not installed"}
    safe_write_log(f"e2fsck -n {partition}")
    rc, out, err = run_text(["e2fsck", "-n", partition])
    dry_out = out.strip()
    if "clean" in (dry_out or "").lower() or rc == 0:
        return {"status": "filesystem appears clean", "dry_rc": rc, "dry_out": dry_out}
    if auto_yes or input("Run e2fsck -f -y to attempt repairs? [y/N]: ").strip().lower() in ("y", "yes"):
        rc2, out2, err2 = run_text(["e2fsck", "-f", "-y", partition])
        return {"rc": rc2, "out": out2.strip(), "err": err2.strip()}
    return {"status": "user declined destructive repair", "dry_rc": rc, "dry_out": dry_out}

def repair_exfat(partition: str, auto_yes: bool = False) -> Dict:
    if which("fsck.exfat"):
        rc, out, err = run_text(["fsck.exfat", "-n", partition])
        dry_out = out.strip()
        if auto_yes or input("Run fsck.exfat to repair? [y/N]: ").strip().lower() in ("y", "yes"):
            rc2, out2, err2 = run_text(["fsck.exfat", partition])
            return {"rc": rc2, "out": out2.strip(), "err": err2.strip()}
        return {"dry_rc": rc, "dry_out": dry_out}
    elif which("fsck.vfat"):
        rc, out, err = run_text(["fsck.vfat", partition])
        return {"rc": rc, "out": out.strip(), "err": err.strip(), "note": "used fsck.vfat fallback"}
    else:
        return {"error": "No exFAT/FAT repair tool installed"}

# -------------------- conservative repair flow --------------------
def repair_flow(partition: str, auto_yes: bool = False, mount_base: str = "/mnt") -> Dict:
    require_root()
    pretty_header(f"Repair Flow: {partition}")
    result: Dict = {"partition": partition, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    if not validate_device_input(partition):
        msg = f"Invalid partition/device: {partition}"
        print(Fore.RED + "❌ " + msg)
        result["error"] = msg
        return result

    info = get_partition_info(partition)
    fstype = info.get("TYPE")
    print(Fore.CYAN + f"ℹ️ Detected filesystem: {safe_str(fstype, '-')}")
    result["fstype"] = fstype

    # try read-only mount first
    mp_ro = create_mountpoint(base=mount_base, name=f"dsk_{os.path.basename(partition)}_ro")
    print(Fore.CYAN + f"ℹ️ Attempting read-only mount at {mp_ro} ...")
    ok, out = attempt_mount(partition, mp_ro, options="ro")
    if ok:
        print(Fore.GREEN + f"✅ Mounted read-only at {mp_ro}")
        result["mounted_ro"] = mp_ro
        return result
    else:
        result["mount_ro_error"] = out.strip()
        safe_write_log(f"mount_ro_failed {partition}: {out.strip()}")
        print(Fore.RED + "❌ Read-only mount failed.")

    # filesystem-specific repair attempts
    if fstype == "ntfs":
        print(Fore.CYAN + "ℹ️ Running ntfsfix (conservative)...")
        res = repair_ntfs(partition, auto_yes=auto_yes)
        result["repair"] = res
        # try mounting with ntfs-3g
        mp_rw = create_mountpoint(base=mount_base, name=f"dsk_{os.path.basename(partition)}_rw")
        ok2, out2 = mount_ntfs_with_ntfs3g(partition, mp_rw)
        if ok2:
            print(Fore.GREEN + f"✅ Mounted with ntfs-3g at {mp_rw}")
            result["mounted"] = mp_rw
        else:
            result["mount_after"] = out2.strip()
            print(Fore.RED + "❌ Mount after ntfsfix failed. Recommendation: connect to Windows and run chkdsk /f /r")

    elif fstype in ("ext4", "ext3", "ext2"):
        print(Fore.CYAN + "ℹ️ Running e2fsck (conservative)...")
        res = repair_extfs(partition, auto_yes=auto_yes)
        result["repair"] = res
        # attempt mount if repair said ok
        mp_rw = create_mountpoint(base=mount_base, name=f"dsk_{os.path.basename(partition)}_rw")
        ok2, out2 = attempt_mount(partition, mp_rw)
        if ok2:
            print(Fore.GREEN + f"✅ Mounted at {mp_rw}")
            result["mounted"] = mp_rw
        else:
            result["mount_after"] = out2.strip()
            print(Fore.RED + "❌ Mount failed after repair.")

    elif fstype in ("exfat", "vfat"):
        print(Fore.CYAN + "ℹ️ Running exFAT/FAT repair helper...")
        res = repair_exfat(partition, auto_yes=auto_yes)
        result["repair"] = res
        mp_rw = create_mountpoint(base=mount_base, name=f"dsk_{os.path.basename(partition)}_rw")
        ok2, out2 = attempt_mount(partition, mp_rw)
        if ok2:
            print(Fore.GREEN + f"✅ Mounted at {mp_rw}")
            result["mounted"] = mp_rw
        else:
            result["mount_after"] = out2.strip()
            print(Fore.RED + "❌ Mount failed after exFAT repair.")

    else:
        print(Fore.YELLOW + "⚠️ Unknown or unsupported filesystem type. Consider imaging with ddrescue.")
        result["note"] = "unsupported fs or unknown type"

    # collect some diagnostics
    parent = get_parent_disk(partition)
    if parent:
        dm = check_dmesg_for_device(parent)
        if dm:
            result["dmesg"] = dm
        sm = smart_check(parent)
        result["smart"] = sm

    return result

# -------------------- imaging --------------------
def image_with_ddrescue(src: str, dest_img: str, mapfile: str, auto_yes: bool = False) -> Dict:
    require_root()
    if not os.path.exists(src):
        return {"error": f"source does not exist: {src}"}
    dd = which("ddrescue") or which("gddrescue")
    if not dd:
        return {"error": "ddrescue (gddrescue) not found; install package 'gddrescue'."}
    if not auto_yes:
        if input(f"Proceed to image {src} -> {dest_img}? This may take a long time. [y/N]: ").strip().lower() not in ("y", "yes"):
            return {"aborted": True}
    os.makedirs(os.path.dirname(dest_img) or ".", exist_ok=True)
    cmd = [dd, "-f", "--logfile", mapfile, src, dest_img]
    safe_write_log(f"ddrescue start {src} -> {dest_img} map {mapfile}")
    try:
        p = subprocess.Popen(cmd)
        p.wait()
        return {"rc": p.returncode}
    except Exception as e:
        return {"error": str(e)}

# -------------------- inspect --------------------
def inspect_partition(partition: str) -> Dict:
    pretty_header(f"Inspect: {partition}")
    if not partition or not partition.startswith("/dev/"):
        print(Fore.RED + "❌ Invalid partition string")
        return {"error": "invalid partition"}
    info = get_partition_info(partition)
    print(json.dumps(info, indent=2))
    parent = get_parent_disk(partition)
    if parent:
        print(Fore.CYAN + f"\nℹ️ Recent dmesg lines for {parent}:")
        dm = check_dmesg_for_device(parent)
        print(dm or Fore.YELLOW + "[i] No dmesg lines found for this device.")
        print(Fore.CYAN + f"\nℹ️ SMART summary for {parent}:")
        sm = smart_check(parent)
        print(json.dumps(sm, indent=2))
    else:
        print(Fore.YELLOW + "[i] Could not determine parent disk")
    return {"blkid": info}

# -------------------- interactive selection --------------------
def choose_partition(prompt: str = "Select a partition:") -> Optional[str]:
    try:
        devs = list_block_devices()
    except Exception as e:
        print(Fore.RED + f"❌ Failed to list block devices: {e}")
        return None
    partitions: List[str] = []
    print(badge_info(prompt))
    idx = 1
    for dev in devs.get("blockdevices", []):
        for part in dev.get("children") or []:
            pname = part.get("name")
            fstype = safe_str(part.get("fstype"))
            size = safe_str(part.get("size"))
            mount = safe_str(part.get("mountpoint"))
            print(f"{idx}) /dev/{pname}  FS:{fstype:<6}  SIZE:{size:<8}  MOUNT:{mount}")
            partitions.append(f"/dev/{pname}")
            idx += 1
    if not partitions:
        print(badge_warn("No partitions available"))
        return None
    while True:
        choice = input("Enter number (or 'q' to cancel): ").strip()
        if choice.lower() in ("q", "quit", "exit"):
            return None
        if not choice.isdigit():
            print(badge_warn("Please enter a valid number"))
            continue
        num = int(choice)
        if 1 <= num <= len(partitions):
            return partitions[num - 1]
        print(badge_warn("Choice out of range"))

# -------------------- detect unmounted partitions --------------------
def detect_unmounted_partitions() -> None:
    try:
        devs = list_block_devices()
    except Exception as e:
        print(Fore.RED + f"❌ Failed to run lsblk: {e}")
        return
    unmounted: List[str] = []
    for dev in devs.get("blockdevices", []):
        for part in dev.get("children") or []:
            if part.get("fstype") and not part.get("mountpoint"):
                unmounted.append(f"/dev/{part['name']}")
    if not unmounted:
        return
    print(badge_warn("Detected unmounted partitions:"))
    for p in unmounted:
        print(" - " + Fore.CYAN + p)
    # only attempt repair if running as root
    if os.geteuid() != 0:
        print(Fore.YELLOW + "⚠️ Not running as root. To attempt repairs now, re-run the tool with sudo.")
        return
    for p in unmounted:
        ans = input(f"Attempt repair on {p}? [y/N]: ").strip().lower()
        if ans in ("y", "yes"):
            res = repair_flow(p, auto_yes=True)
            print(Fore.CYAN + "\n[Summary]")
            print(json.dumps(res, indent=2))

# -------------------- interactive menu --------------------
def interactive_menu() -> None:
    banner()
    detect_unmounted_partitions()
    while True:
        print("\n=== " + Fore.MAGENTA + "DSK Repair Menu" + Fore.RESET + " ===")
        print("1) List all block devices")
        print("2) List drives (whole disks)")
        print("3) Inspect a partition")
        print("4) Repair a partition")
        print("5) Repair and Mount a partition")
        print("6) Create disk image with ddrescue")
        print("7) Mount a partition manually")
        print("8) Exit")
        choice = input(Fore.CYAN + "Select an option [1-8]: " + Fore.RESET).strip()

        try:
            if choice == "1":
                try:
                    devs = list_block_devices()
                    print_block_devices(devs)
                except Exception as e:
                    print(badge_error(f"lsblk failed: {e}"))

            elif choice == "2":
                try:
                    list_drives()
                except Exception as e:
                    print(badge_error(f"lsblk failed: {e}"))

            elif choice == "3":
                part = choose_partition("Choose partition to inspect")
                if part:
                    inspect_partition(part)

            elif choice == "4":
                if os.geteuid() != 0:
                    print(Fore.RED + "❌ Repairing requires root. Re-run with sudo.")
                    continue
                part = choose_partition("Choose partition to repair")
                if part:
                    res = repair_flow(part, auto_yes=False)
                    print(Fore.CYAN + "\n[Summary]")
                    print(json.dumps(res, indent=2))

            elif choice == "5":
                if os.geteuid() != 0:
                    print(Fore.RED + "❌ Repairing requires root. Re-run with sudo.")
                    continue
                part = choose_partition("Choose partition to repair and mount")
                if part:
                    res = repair_flow(part, auto_yes=True)
                    # if not mounted, try a final mount attempt
                    if res.get("mounted"):
                        print(badge_success(f"Mounted at {res['mounted']}"))
                    else:
                        mp_final = create_mountpoint(name=f"dsk_{os.path.basename(part)}_final")
                        ok, out = attempt_mount(part, mp_final)
                        if ok:
                            print(badge_success(f"Mounted {part} at {mp_final}"))
                            res["mounted"] = mp_final
                        else:
                            print(badge_error(f"Final mount attempt failed: {out}"))
                            res["mount_final_error"] = out.strip()
                    print(Fore.CYAN + "\n[Summary]")
                    print(json.dumps(res, indent=2))

            elif choice == "6":
                if os.geteuid() != 0:
                    print(Fore.RED + "❌ Imaging requires root. Re-run with sudo.")
                    continue
                src = input("Source device (e.g., /dev/sdb): ").strip()
                dest = input("Destination image path (e.g., /path/to/image.img): ").strip()
                if not src or not dest:
                    print(badge_warn("Source and destination are required"))
                    continue
                mapfile = input("Mapfile path [press Enter to use dest + .map]: ").strip() or (dest + ".map")
                res = image_with_ddrescue(src, dest, mapfile, auto_yes=False)
                print(Fore.CYAN + "\n[Result]")
                print(json.dumps(res, indent=2))

            elif choice == "7":
                if os.geteuid() != 0:
                    print(Fore.RED + "❌ Mounting requires root. Re-run with sudo.")
                    continue
                part = choose_partition("Choose partition to mount")
                if not part:
                    continue
                mp = input("Enter mountpoint (leave blank for auto under /mnt): ").strip()
                if not mp:
                    mp = create_mountpoint(name=f"dsk_{os.path.basename(part)}_manual")
                os.makedirs(mp, exist_ok=True)
                ok, out = attempt_mount(part, mp)
                if ok:
                    print(badge_success(f"Mounted {part} at {mp}"))
                else:
                    print(badge_error(f"Mount failed:\n{out}"))
                    print(badge_info("Tip: try option 5 to attempt repair then mount."))

            elif choice == "8":
                print(badge_info("Exiting DSK Repair. Goodbye!"))
                break

            else:
                print(badge_warn("Invalid choice — enter a number 1-8"))

        except KeyboardInterrupt:
            print("\n" + badge_warn("Interrupted by user — returning to menu"))
        except Exception as e:
            print(badge_error(f"Unexpected error: {e}"))

# -------------------- CLI parsing (one-shot) --------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="DSK Repair - Intelligent Disk Repair Utility")
    p.add_argument("--version", action="store_true", help="Show version")
    p.add_argument("--list", action="store_true", help="List block devices")
    p.add_argument("--drives", action="store_true", help="List only drives (whole disks)")
    p.add_argument("--inspect", metavar="PART", help="Inspect a partition (e.g., /dev/sdb2)")
    p.add_argument("--repair", metavar="PART", help="Repair a partition (requires root)")
    p.add_argument("--image", nargs=2, metavar=("SRC", "DEST"), help="Create image of SRC to DEST using ddrescue (requires root)")
    p.add_argument("--mapfile", help="Mapfile for ddrescue (used with --image)")
    p.add_argument("--yes", action="store_true", help="Assume yes to prompts")
    return p

def main(argv: Optional[List[str]] = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)

    # no args = interactive
    if len(argv) == 0:
        try:
            interactive_menu()
        except KeyboardInterrupt:
            print(badge_error("Interrupted by user"))
        return

    # one-shot CLI
    if args.version:
        banner()
        print(Fore.CYAN + "Version: " + VERSION)
        return
    if args.list:
        try:
            devs = list_block_devices()
            print_block_devices(devs)
        except Exception as e:
            print(badge_error(f"lsblk failed: {e}"))
        return
    if args.drives:
        try:
            list_drives()
        except Exception as e:
            print(badge_error(f"lsblk failed: {e}"))
        return
    if args.inspect:
        inspect_partition(args.inspect)
        return
    if args.repair:
        require_root()
        res = repair_flow(args.repair, auto_yes=args.yes)
        print(json.dumps(res, indent=2))
        return
    if args.image:
        require_root()
        src, dest = args.image
        mapfile = args.mapfile or (dest + ".map")
        res = image_with_ddrescue(src, dest, mapfile, auto_yes=args.yes)
        print(json.dumps(res, indent=2))
        return

    parser.print_help()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(badge_error("\nInterrupted by user"))

