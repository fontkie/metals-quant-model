"""
show_layout.py
----------------
Print a clean repo folder tree using ASCII only (Windows-safe).

Usage:
  python src/show_layout.py                          # default (excludes noisy dirs)
  python src/show_layout.py --all                    # include everything
  python src/show_layout.py --exclude data outputs   # custom excludes
  python src/show_layout.py > repo_structure.txt     # save to file
"""

from pathlib import Path
import argparse
import sys

DEFAULT_EXCLUDES = {
    ".git", ".venv", "env", "venv", "__pycache__", ".idea", ".vscode",
    "data", "outputs"  # excluded by default to keep output compact
}

def safe_print_line(s: str):
    # Replace characters the current console can't encode
    enc = sys.stdout.encoding or "utf-8"
    print(s.encode(enc, errors="replace").decode(enc, errors="replace"))

def print_tree(path: Path, prefix: str = "", excludes=None):
    excludes = excludes or set()
    try:
        entries = sorted([p for p in path.iterdir() if p.name not in excludes], key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return
    for i, entry in enumerate(entries):
        is_last = (i == len(entries) - 1)
        connector = "+-- " if is_last else "+-- "
        safe_print_line(prefix + connector + entry.name)
        if entry.is_dir():
            extension = "    " if is_last else "|   "
            print_tree(entry, prefix + extension, excludes=excludes)

def main():
    parser = argparse.ArgumentParser(description="ASCII-only repo tree printer")
    parser.add_argument("--all", action="store_true", help="include all folders (no default excludes)")
    parser.add_argument("--exclude", nargs="*", default=None, help="additional names to exclude")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    excludes = set() if args.all else set(DEFAULT_EXCLUDES)
    if args.exclude:
        excludes |= set(args.exclude)

    safe_print_line(f"\nRepo structure for: {root.name}\n")
    print_tree(root, excludes=excludes)
    safe_print_line("\nTip: run with --all to include data/ and outputs/ if needed.\n")

if __name__ == "__main__":
    main()
