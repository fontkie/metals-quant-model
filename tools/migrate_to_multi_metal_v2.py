"""
Multi-Metal Migration Script v2
================================
1. Standardizes copper to lowercase (Config/copper, outputs/copper)
2. Updates all references in batch files and configs
3. Creates aluminum structure (lowercase ali)
4. Safe with dry-run mode and rollback instructions

Run from: C:\Code\Metals
Usage:
    python tools\migrate_to_multi_metal_v2.py --check     # Dry run - see what happens
    python tools\migrate_to_multi_metal_v2.py --execute   # Do the migration

Author: Claude + Kieran
Date: November 21, 2025
"""

import os
import sys
import shutil
import argparse
from pathlib import Path
import re
import json
from datetime import datetime


def get_project_root():
    """Get project root (assumes script is in tools/)"""
    return Path(__file__).parent.parent


def create_backup_manifest(root: Path) -> dict:
    """Create manifest of current state for rollback"""
    manifest = {
        "timestamp": datetime.now().isoformat(),
        "directories": {
            "Config/Copper": (root / "Config/Copper").exists(),
            "outputs/Copper": (root / "outputs/Copper").exists(),
            "Config/copper": (root / "Config/copper").exists(),
            "outputs/copper": (root / "outputs/copper").exists(),
        },
        "batch_files": [],
    }

    scripts_dir = root / "scripts"
    if scripts_dir.exists():
        for bat_file in scripts_dir.glob("*.bat"):
            content = bat_file.read_text(encoding="utf-8", errors="ignore")
            manifest["batch_files"].append(
                {
                    "name": bat_file.name,
                    "has_capital_copper": "Config\\Copper" in content
                    or "outputs\\Copper" in content,
                }
            )

    return manifest


def check_current_state(root: Path) -> dict:
    """Check current directory structure"""

    results = {
        "status": "OK",
        "errors": [],
        "warnings": [],
        "found": [],
        "needs_rename": False,
    }

    # Check what exists
    config_copper_cap = root / "Config/Copper"
    config_copper_low = root / "Config/copper"
    outputs_copper_cap = root / "outputs/Copper"
    outputs_copper_low = root / "outputs/copper"

    if config_copper_cap.exists():
        results["found"].append("✅ Config/Copper (capital C) exists")
        results["needs_rename"] = True

    if config_copper_low.exists():
        results["found"].append("✅ Config/copper (lowercase) exists")
        if config_copper_cap.exists():
            results["errors"].append(
                "❌ BOTH Config/Copper AND Config/copper exist! Manual cleanup needed."
            )
            results["status"] = "ERROR"

    if outputs_copper_cap.exists():
        results["found"].append("✅ outputs/Copper (capital C) exists")
        results["needs_rename"] = True

    if outputs_copper_low.exists():
        results["found"].append("✅ outputs/copper (lowercase) exists")
        if outputs_copper_cap.exists():
            results["errors"].append(
                "❌ BOTH outputs/Copper AND outputs/copper exist! Manual cleanup needed."
            )
            results["status"] = "ERROR"

    data_copper = root / "Data/copper"
    if data_copper.exists():
        results["found"].append("✅ Data/copper (already lowercase)")
    else:
        results["errors"].append("❌ MISSING: Data/copper")
        results["status"] = "ERROR"

    return results


def rename_copper_to_lowercase(root: Path, dry_run: bool = True) -> list:
    """Rename Config/Copper and outputs/Copper to lowercase"""

    actions = []

    # Config/Copper -> Config/copper
    source = root / "Config/Copper"
    dest = root / "Config/copper"

    if source.exists() and not dest.exists():
        actions.append(f"RENAME: Config/Copper -> Config/copper")
        if not dry_run:
            source.rename(dest)
            actions.append("  ✅ Renamed successfully")
    elif source.exists() and dest.exists():
        actions.append(
            "ERROR: Both Config/Copper and Config/copper exist - manual cleanup needed"
        )
    elif dest.exists():
        actions.append("SKIP: Config/copper already exists (lowercase)")

    # outputs/Copper -> outputs/copper
    source = root / "outputs/Copper"
    dest = root / "outputs/copper"

    if source.exists() and not dest.exists():
        actions.append(f"RENAME: outputs/Copper -> outputs/copper")
        if not dry_run:
            source.rename(dest)
            actions.append("  ✅ Renamed successfully")
    elif source.exists() and dest.exists():
        actions.append(
            "ERROR: Both outputs/Copper and outputs/copper exist - manual cleanup needed"
        )
    elif dest.exists():
        actions.append("SKIP: outputs/copper already exists (lowercase)")

    return actions


def update_batch_files_to_lowercase(root: Path, dry_run: bool = True) -> list:
    """Update all batch files to use lowercase paths"""

    actions = []
    scripts_dir = root / "scripts"

    if not scripts_dir.exists():
        actions.append("ERROR: scripts/ directory not found")
        return actions

    for bat_file in scripts_dir.glob("*.bat"):
        content = bat_file.read_text(encoding="utf-8", errors="ignore")
        original_content = content

        # Replace capital Copper with lowercase copper
        content = content.replace("Config\\Copper\\", "Config\\copper\\")
        content = content.replace("Config/Copper/", "Config/copper/")
        content = content.replace("outputs\\Copper\\", "outputs\\copper\\")
        content = content.replace("outputs/Copper/", "outputs/copper/")

        if content != original_content:
            actions.append(f"UPDATE: scripts/{bat_file.name}")
            if not dry_run:
                bat_file.write_text(content, encoding="utf-8")
                actions.append(f"  ✅ Updated paths to lowercase")
        else:
            actions.append(
                f"SKIP: scripts/{bat_file.name} (already lowercase or no paths)"
            )

    return actions


def update_config_files_to_lowercase(root: Path, dry_run: bool = True) -> list:
    """Update all config files to use lowercase paths"""

    actions = []
    config_dir = root / "Config/copper"

    if not config_dir.exists():
        # Try capital C version
        config_dir = root / "Config/Copper"
        if not config_dir.exists():
            actions.append("ERROR: No copper config directory found")
            return actions

    # Update root-level YAML files
    for yaml_file in config_dir.glob("*.yaml"):
        content = yaml_file.read_text(encoding="utf-8")
        original_content = content

        # Replace capital paths with lowercase
        content = content.replace("outputs/Copper/", "outputs/copper/")
        content = content.replace("outputs\\Copper\\", "outputs\\copper\\")
        content = content.replace("Config/Copper/", "Config/copper/")
        content = content.replace("Config\\Copper\\", "Config\\copper\\")

        if content != original_content:
            actions.append(f"UPDATE: Config/copper/{yaml_file.name}")
            if not dry_run:
                yaml_file.write_text(content, encoding="utf-8")
                actions.append(f"  ✅ Updated paths to lowercase")

    # Update portfolio subfolder if exists
    portfolio_dir = config_dir / "portfolio"
    if portfolio_dir.exists():
        for yaml_file in portfolio_dir.glob("*.yaml"):
            content = yaml_file.read_text(encoding="utf-8")
            original_content = content

            content = content.replace("outputs/Copper/", "outputs/copper/")
            content = content.replace("outputs\\Copper\\", "outputs\\copper\\")

            if content != original_content:
                actions.append(f"UPDATE: Config/copper/portfolio/{yaml_file.name}")
                if not dry_run:
                    yaml_file.write_text(content, encoding="utf-8")
                    actions.append(f"  ✅ Updated paths to lowercase")

    return actions


def create_aluminum_structure(root: Path, dry_run: bool = True) -> list:
    """Create aluminum directory structure (lowercase ali)"""

    actions = []

    dirs_to_create = [
        "Config/ali",
        "Config/ali/portfolio",
        "Data/ali",
        "Data/ali/pricing",
        "Data/ali/pricing/canonical",
        "Data/ali/fundamentals",
        "Data/ali/fundamentals/canonical",
        "outputs/ali",
        "outputs/ali/TrendMedium_v2",
        "outputs/ali/MomentumCore_v2",
        "outputs/ali/RangeFader_v5",
        "outputs/ali/TightStocks_v1",
        "outputs/ali/VolCore_v1",
        "outputs/ali/Portfolio",
        "outputs/ali/Portfolio/BaselineEqualWeight",
    ]

    for dir_path in dirs_to_create:
        full_path = root / dir_path
        if not full_path.exists():
            actions.append(f"CREATE: {dir_path}")
            if not dry_run:
                full_path.mkdir(parents=True, exist_ok=True)
        else:
            actions.append(f"EXISTS: {dir_path}")

    return actions


def copy_copper_configs_to_ali(root: Path, dry_run: bool = True) -> list:
    """Copy copper configs to aluminum with path updates"""

    actions = []

    copper_config = root / "Config/copper"
    ali_config = root / "Config/ali"

    if not copper_config.exists():
        actions.append(
            "ERROR: Config/copper not found - run lowercase standardization first"
        )
        return actions

    # Copy root-level YAML files
    yaml_files = list(copper_config.glob("*.yaml"))

    for yaml_file in yaml_files:
        dest_file = ali_config / yaml_file.name
        actions.append(
            f"COPY: Config/copper/{yaml_file.name} -> Config/ali/{yaml_file.name}"
        )

        if not dry_run:
            content = yaml_file.read_text(encoding="utf-8")
            content = _update_config_for_ali(content)
            dest_file.write_text(content, encoding="utf-8")
            actions.append(f"  ✅ Updated metal and paths to 'ali'")

    # Copy portfolio subfolder
    portfolio_dir = copper_config / "portfolio"
    if portfolio_dir.exists():
        ali_portfolio_dir = ali_config / "portfolio"

        for yaml_file in portfolio_dir.glob("*.yaml"):
            dest_file = ali_portfolio_dir / yaml_file.name
            actions.append(
                f"COPY: Config/copper/portfolio/{yaml_file.name} -> Config/ali/portfolio/{yaml_file.name}"
            )

            if not dry_run:
                content = yaml_file.read_text(encoding="utf-8")
                content = _update_config_for_ali(content)
                dest_file.write_text(content, encoding="utf-8")
                actions.append(f"  ✅ Updated metal and paths to 'ali'")

    return actions


def _update_config_for_ali(content: str) -> str:
    """Helper to update config content for aluminum"""

    # Replace metal: copper with metal: ali
    content = re.sub(r"metal:\s*copper", "metal: ali", content, flags=re.IGNORECASE)

    # Replace copper paths with ali paths
    content = content.replace("outputs/copper/", "outputs/ali/")
    content = content.replace("outputs\\copper\\", "outputs\\ali\\")
    content = content.replace("Data/copper/", "Data/ali/")
    content = content.replace("Data\\copper\\", "Data\\ali\\")
    content = content.replace("Config/copper/", "Config/ali/")
    content = content.replace("Config\\copper\\", "Config\\ali\\")

    return content


def create_aluminum_batch_files(root: Path, dry_run: bool = True) -> list:
    """Create aluminum batch files"""

    actions = []
    scripts_dir = root / "scripts"

    batch_mappings = {
        "run_trendmedium_v2.bat": "run_trendmedium_v2_ali.bat",
        "run_momentumcore_v2.bat": "run_momentumcore_v2_ali.bat",
        "run_rangefader_v5.bat": "run_rangefader_v5_ali.bat",
        "run_tightstocks_v1.bat": "run_tightstocks_v1_ali.bat",
        "run_build_baseline_portfolio.bat": "run_build_baseline_portfolio_ali.bat",
    }

    for copper_bat, ali_bat in batch_mappings.items():
        copper_path = scripts_dir / copper_bat
        ali_path = scripts_dir / ali_bat

        if not copper_path.exists():
            actions.append(f"SKIP: {copper_bat} (not found)")
            continue

        if ali_path.exists():
            actions.append(f"SKIP: {ali_bat} (already exists)")
            continue

        actions.append(f"CREATE: scripts/{ali_bat}")

        if not dry_run:
            content = copper_path.read_text(encoding="utf-8", errors="ignore")

            # Replace paths
            content = content.replace("Data\\copper\\", "Data\\ali\\")
            content = content.replace("Data/copper/", "Data/ali/")
            content = content.replace("Config\\copper\\", "Config\\ali\\")
            content = content.replace("Config/copper/", "Config/ali/")
            content = content.replace("outputs\\copper\\", "outputs\\ali\\")
            content = content.replace("outputs/copper/", "outputs/ali/")

            # Replace file names
            content = content.replace("copper_lme_", "ali_lme_")
            content = content.replace("copper_shfe_", "ali_shfe_")
            content = content.replace("copper_comex_", "ali_comex_")
            content = content.replace("copper_balance", "ali_balance")
            content = content.replace("copper_demand", "ali_demand")

            # Replace text
            content = content.replace("COPPER", "ALUMINUM")
            content = content.replace("Copper", "Aluminum")

            ali_path.write_text(content, encoding="utf-8")
            actions.append(f"  ✅ Created from {copper_bat}")

    return actions


def verify_migration(root: Path) -> dict:
    """Verify migration completed successfully"""

    results = {"status": "OK", "checks": []}

    # Check lowercase copper exists
    if (root / "Config/copper").exists():
        results["checks"].append("✅ Config/copper exists (lowercase)")
    else:
        results["checks"].append("❌ Config/copper missing")
        results["status"] = "ERROR"

    if (root / "outputs/copper").exists():
        results["checks"].append("✅ outputs/copper exists (lowercase)")
    else:
        results["checks"].append("❌ outputs/copper missing")
        results["status"] = "ERROR"

    # Check aluminum created
    if (root / "Config/ali").exists():
        results["checks"].append("✅ Config/ali exists")
    else:
        results["checks"].append("❌ Config/ali missing")
        results["status"] = "ERROR"

    if (root / "outputs/ali").exists():
        results["checks"].append("✅ outputs/ali exists")
    else:
        results["checks"].append("❌ outputs/ali missing")
        results["status"] = "ERROR"

    # Check no capital Copper remains
    if (root / "Config/Copper").exists():
        results["checks"].append(
            "⚠️ Config/Copper still exists (expected to be renamed)"
        )

    if (root / "outputs/Copper").exists():
        results["checks"].append(
            "⚠️ outputs/Copper still exists (expected to be renamed)"
        )

    # Check batch files exist
    scripts_dir = root / "scripts"
    if (scripts_dir / "run_trendmedium_v2_ali.bat").exists():
        results["checks"].append("✅ Aluminum batch files created")
    else:
        results["checks"].append("⚠️ Aluminum batch files not found")

    return results


def main():
    parser = argparse.ArgumentParser(description="Multi-Metal Migration Script v2")
    parser.add_argument(
        "--check", action="store_true", help="Dry run - show what would happen"
    )
    parser.add_argument("--execute", action="store_true", help="Execute migration")
    parser.add_argument(
        "--root", type=str, default=None, help="Project root (default: auto-detect)"
    )

    args = parser.parse_args()

    if not args.check and not args.execute:
        print("Usage:")
        print("  python tools\\migrate_to_multi_metal_v2.py --check")
        print("  python tools\\migrate_to_multi_metal_v2.py --execute")
        return 1

    # Get project root
    if args.root:
        root = Path(args.root)
    else:
        root = get_project_root()

    print("=" * 70)
    print("MULTI-METAL MIGRATION SCRIPT v2")
    print("=" * 70)
    print(f"\nProject root: {root}")
    print()

    # Step 1: Check current state
    print("-" * 70)
    print("STEP 1: Current State Check")
    print("-" * 70)

    current_state = check_current_state(root)

    for item in current_state["found"]:
        print(item)

    for warning in current_state["warnings"]:
        print(warning)

    for error in current_state["errors"]:
        print(error)

    if current_state["status"] == "ERROR":
        print("\n❌ ERRORS FOUND - Fix manually before proceeding")
        return 1

    print()
    if current_state["needs_rename"]:
        print("📋 Capital Copper directories found - will standardize to lowercase")
    else:
        print("✅ Already using lowercase copper")

    # Dry run mode
    if args.check:
        print("\n" + "=" * 70)
        print("DRY RUN MODE - Showing what would happen")
        print("=" * 70)

        print("\n" + "-" * 70)
        print("PHASE 1: Standardize Copper to Lowercase")
        print("-" * 70)

        print("\nRename directories:")
        for action in rename_copper_to_lowercase(root, dry_run=True):
            print(f"  {action}")

        print("\nUpdate batch files:")
        for action in update_batch_files_to_lowercase(root, dry_run=True):
            print(f"  {action}")

        print("\nUpdate config files:")
        for action in update_config_files_to_lowercase(root, dry_run=True):
            print(f"  {action}")

        print("\n" + "-" * 70)
        print("PHASE 2: Create Aluminum Structure")
        print("-" * 70)

        print("\nCreate directories:")
        for action in create_aluminum_structure(root, dry_run=True):
            print(f"  {action}")

        print("\nCopy configs:")
        for action in copy_copper_configs_to_ali(root, dry_run=True):
            print(f"  {action}")

        print("\nCreate batch files:")
        for action in create_aluminum_batch_files(root, dry_run=True):
            print(f"  {action}")

        print("\n" + "=" * 70)
        print("✅ DRY RUN COMPLETE - No changes made")
        print("=" * 70)
        print("\nTo execute: python tools\\migrate_to_multi_metal_v2.py --execute")

        return 0

    # Execute migration
    if args.execute:
        print("\n" + "=" * 70)
        print("EXECUTING MIGRATION")
        print("=" * 70)

        # Create backup manifest
        manifest = create_backup_manifest(root)
        manifest_path = root / "migration_backup_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"\n✅ Backup manifest created: {manifest_path}")

        # Phase 1: Standardize copper
        print("\n" + "-" * 70)
        print("PHASE 1: Standardizing Copper to Lowercase")
        print("-" * 70)

        print("\nRenaming directories...")
        for action in rename_copper_to_lowercase(root, dry_run=False):
            print(f"  {action}")

        print("\nUpdating batch files...")
        for action in update_batch_files_to_lowercase(root, dry_run=False):
            print(f"  {action}")

        print("\nUpdating config files...")
        for action in update_config_files_to_lowercase(root, dry_run=False):
            print(f"  {action}")

        # Phase 2: Create aluminum
        print("\n" + "-" * 70)
        print("PHASE 2: Creating Aluminum Structure")
        print("-" * 70)

        print("\nCreating directories...")
        for action in create_aluminum_structure(root, dry_run=False):
            print(f"  {action}")

        print("\nCopying configs...")
        for action in copy_copper_configs_to_ali(root, dry_run=False):
            print(f"  {action}")

        print("\nCreating batch files...")
        for action in create_aluminum_batch_files(root, dry_run=False):
            print(f"  {action}")

        # Verify
        print("\n" + "-" * 70)
        print("VERIFICATION")
        print("-" * 70)

        verification = verify_migration(root)
        for check in verification["checks"]:
            print(check)

        if verification["status"] == "OK":
            print("\n" + "=" * 70)
            print("✅ MIGRATION COMPLETE")
            print("=" * 70)

            print("\nNEXT STEPS:")
            print("\n1. Test copper still works:")
            print("   cd C:\\Code\\Metals")
            print("   scripts\\run_trendmedium_v2.bat")
            print()
            print("2. Commit to Git:")
            print("   git add -A")
            print(
                '   git commit -m "Standardize to lowercase + add aluminum structure"'
            )
            print()
            print("3. Prepare aluminum data:")
            print("   - Data\\ali\\pricing\\canonical\\ali_lme_3mo.canonical.csv")
            print(
                "   - Data\\ali\\pricing\\canonical\\ali_lme_3mo_volume.canonical.csv"
            )
            print(
                "   - Data\\ali\\pricing\\canonical\\ali_lme_1mo_impliedvol.canonical.csv"
            )
            print()
            print("4. Test aluminum (after data ready):")
            print("   scripts\\run_trendmedium_v2_ali.bat")

        else:
            print("\n⚠️ Some verification checks failed - review above")

        return 0


if __name__ == "__main__":
    sys.exit(main())
