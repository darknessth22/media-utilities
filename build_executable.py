#!/usr/bin/env python3
"""
Build script for creating Windows executable and installer for Media Utility GUI.
Includes size monitoring and pinned ffmpeg with checksum verification.
"""

import os
import sys
import subprocess
import urllib.request
import zipfile
import shutil
import json
import hashlib
from pathlib import Path
from datetime import datetime

def print_step(step_name):
    """Print a formatted step header"""
    print(f"\n{'='*60}")
    print(f"STEP: {step_name}")
    print(f"{'='*60}")

def load_build_config():
    """Load build configuration from build_config.json"""
    print_step("Loading Build Configuration")
    try:
        with open('build_config.json') as f:
            config = json.load(f)
        print("✅ Build configuration loaded.")
        return config
    except Exception as e:
        print(f"❌ Failed to load build_config.json: {e}")
        sys.exit(1)

def get_app_version():
    """Detect version from environment or core/version.py"""
    version = os.environ.get('APP_VERSION')
    if version:
        print(f"✅ Version detected from environment: {version}")
        return version
    
    try:
        # Add current dir to path to import core.version
        sys.path.append(os.getcwd())
        from core.version import VERSION
        print(f"✅ Version detected from core/version.py: {VERSION}")
        return VERSION
    except ImportError:
        print("⚠️ core/version.py not found, using default 1.0.0")
        return "1.0.0"

def download_ffmpeg_pinned(cfg):
    """Download pinned FFmpeg with checksum verification"""
    print_step("Ensuring FFmpeg (Pinned)")
    
    bin_dir = Path("bin")
    bin_dir.mkdir(exist_ok=True)
    
    ffmpeg_exe = bin_dir / "ffmpeg.exe"
    ffprobe_exe = bin_dir / "ffprobe.exe"
    
    if ffmpeg_exe.exists() and ffprobe_exe.exists():
        print("✅ Pinned FFmpeg binaries already exist in bin/, skipping download")
        return True

    print(f"📥 Downloading FFmpeg {cfg['version']}...")
    zip_path = Path("ffmpeg.zip")
    sha_path = Path("ffmpeg.zip.sha256")
    
    try:
        # Download ZIP
        urllib.request.urlretrieve(cfg['url'], zip_path)
        
        # Download SHA256
        urllib.request.urlretrieve(cfg['sha256_url'], sha_path)
        
        # Verify SHA256
        with open(sha_path, 'r') as f:
            expected_hash = f.read().strip().split()[0].lower()
        
        sha256_hash = hashlib.sha256()
        with open(zip_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        actual_hash = sha256_hash.hexdigest().lower()
        
        if actual_hash != expected_hash:
            print(f"❌ SHA256 verification FAILED!")
            print(f"Expected: {expected_hash}")
            print(f"Actual:   {actual_hash}")
            return False
        
        print("✅ SHA256 verification passed.")
        
        # Extract binaries
        print("Extracting binaries...")
        prefix = cfg['strip_prefix']
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.namelist():
                if member.startswith(prefix) and member.endswith(('.exe')):
                    filename = os.path.basename(member)
                    with zip_ref.open(member) as source, open(bin_dir / filename, "wb") as target:
                        shutil.copyfileobj(source, target)
        
        print(f"✅ Extracted: {ffmpeg_exe.name}, {ffprobe_exe.name}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to download/extract FFmpeg: {e}")
        return False
    finally:
        if zip_path.exists(): zip_path.unlink()
        if sha_path.exists(): sha_path.unlink()

def generate_icon():
    """Render assets/icons/dashboard.svg → icon.ico via PySide6 + Pillow (no native Cairo needed)."""
    print_step("Generating icon.ico from dashboard.svg")

    helper = Path("_gen_icon.py")
    if not helper.exists():
        print(f"⚠️ {helper} not found — keeping existing icon.ico")
        return

    try:
        subprocess.check_call([sys.executable, str(helper)])
    except subprocess.CalledProcessError as exc:
        print(f"⚠️ Icon generation failed (exit {exc.returncode}) — keeping existing icon.ico")


def build_executable():
    """Build the executable using PyInstaller"""
    print_step("Building Executable with PyInstaller")

    try:
        # Clean previous builds
        if os.path.exists('dist'):
            shutil.rmtree('dist')
        if os.path.exists('build'):
            shutil.rmtree('build')

        # Build using spec file
        subprocess.check_call([sys.executable, "-m", "PyInstaller", "media_util_gui.spec", "--clean"])

        print("✅ Executable built successfully!")
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to build executable: {e}")
        return False

def compile_installer(version):
    """Compile Inno Setup installer"""
    print_step("Compiling Inno Setup Installer")
    
    iscc = shutil.which('iscc') or r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
    if not os.path.exists(iscc):
        print(f"⚠️ ISCC.exe not found at {iscc}. Please install Inno Setup 6.")
        print("Skipping installer compilation.")
        return True # Don't fail the whole build if just installer fails due to missing tool
        
    try:
        subprocess.check_call([iscc, f'/DAppVersion={version}', 'installer.iss'])
        print("✅ Installer compiled successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to compile installer: {e}")
        return False

def measure_sizes(dist_dir, installer_path):
    """Measure sizes of installed files and installer"""
    print_step("Measuring Sizes")
    
    dist_path = Path(dist_dir)
    if not dist_path.exists():
        print(f"⚠️ {dist_dir} not found, skipping measurements.")
        return 0, 0, []
        
    installed_mb = sum(f.stat().st_size for f in dist_path.rglob('*') if f.is_file()) / 1e6
    
    inst_path = Path(installer_path)
    installer_mb = inst_path.stat().st_size / 1e6 if inst_path.exists() else 0
    
    top10 = sorted([(p, p.stat().st_size/1e6) for p in dist_path.rglob('*') if p.is_file()],
                   key=lambda x: x[1], reverse=True)[:10]
    
    print(f"Installer: {installer_mb:.2f} MB")
    print(f"Installed: {installed_mb:.2f} MB")
    print("Top 5 contributors:")
    for p, mb in top10[:5]:
        print(f"  {mb:6.2f} MB  {p.relative_to(dist_path)}")
        
    return installer_mb, installed_mb, top10

def check_budget(installer_mb, installed_mb, top10):
    """Enforce size budget from size-budget.json"""
    budget_file = Path('size-budget.json')
    
    if not budget_file.exists():
        print_step("Seeding Size Budget")
        budget = {
            "installer_mb": round(installer_mb, 1),
            "installed_mb": round(installed_mb, 1),
            "tolerance_pct": 5,
            "generated_at": datetime.now().isoformat()
        }
        with open(budget_file, 'w') as f:
            json.dump(budget, f, indent=2)
        print(f"✅ Seeded {budget_file} with current measurements.")
        print("⚠️ Commit this file to enforce these limits in future builds.")
        return True

    with open(budget_file) as f:
        budget = json.load(f)
        
    tol = 1 + budget.get('tolerance_pct', 5) / 100
    failures = []
    
    if installer_mb > budget['installer_mb'] * tol:
        failures.append(f"Installer {installer_mb:.1f} MB > budget {budget['installer_mb']} MB (x{tol})")
    if installed_mb > budget['installed_mb'] * tol:
        failures.append(f"Installed {installed_mb:.1f} MB > budget {budget['installed_mb']} MB (x{tol})")
        
    if failures:
        print("\n❌ BUILD FAILED — size budget exceeded:")
        for f in failures: print(f"  {f}")
        print("\nTop 10 contributors:")
        for p, mb in top10: print(f"  {mb:6.2f} MB  {p}")
        sys.exit(1)
    
    print("✅ Size budget check passed.")
    return True

def write_size_report(installer_mb, installed_mb, top10):
    """Write build artifact dist/size-report.json"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "installer_mb": installer_mb,
        "installed_mb": installed_mb,
        "top_contributors": [{"path": str(p), "mb": mb} for p, mb in top10]
    }
    report_path = Path('dist/size-report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"✅ Size report written to {report_path}")

def main():
    """Main build process"""
    print("🚀 Media Utility - Windows Build Pipeline")
    print("=" * 60)
    
    if sys.platform != "win32":
        print("❌ This build pipeline requires Windows.")
        sys.exit(1)
    
    config = load_build_config()
    version = get_app_version()
    
    # Step 2: Download ffmpeg
    if not download_ffmpeg_pinned(config['ffmpeg']):
        sys.exit(1)

    # Step 3: Regenerate icon from in-app dashboard.svg
    generate_icon()

    # Step 4: PyInstaller
    if not build_executable():
        sys.exit(1)
        
    # Step 5: Inno Setup
    if not compile_installer(version):
        sys.exit(1)

    # Step 6: Measure
    # Output of PyInstaller with COLLECT(name='MediaUtility') is in dist/MediaUtility
    installer_path = "Output/MediaUtility_Setup.exe" # Inno Setup default output
    # Check if installer was actually created elsewhere (custom script might use different path)
    if not os.path.exists(installer_path):
        # installer.iss doesn't specify OutputDir, so it's Output/ by default
        # but let's be flexible
        if os.path.exists("installer/MediaUtility_Setup.exe"):
            installer_path = "installer/MediaUtility_Setup.exe"

    installer_mb, installed_mb, top10 = measure_sizes("dist/MediaUtility", installer_path)

    # Step 7: Budget
    check_budget(installer_mb, installed_mb, top10)

    # Step 8: Report
    write_size_report(installer_mb, installed_mb, top10)
    
    print("\n🎉 Build Complete!")
    print(f"Installer: {os.path.abspath(installer_path)}")

if __name__ == "__main__":
    main()
