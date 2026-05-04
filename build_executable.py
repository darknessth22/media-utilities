#!/usr/bin/env python3
"""
Build script for creating Windows executable and installer for Videl.
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
        print("[OK] Build configuration loaded.")
        return config
    except Exception as e:
        print(f"[FAIL] Failed to load build_config.json: {e}")
        sys.exit(1)

def get_app_version():
    """Detect version from environment or core/version.py"""
    version = os.environ.get('APP_VERSION')
    if version:
        print(f"[OK] Version detected from environment: {version}")
        return version
    
    try:
        # Add current dir to path to import core.version
        sys.path.append(os.getcwd())
        from core.version import VERSION
        print(f"[OK] Version detected from core/version.py: {VERSION}")
        return VERSION
    except ImportError:
        print("[WARN] core/version.py not found, using default 1.0.0")
        return "1.0.0"

def download_ffmpeg_pinned(cfg):
    """Download pinned FFmpeg with checksum verification"""
    print_step("Ensuring FFmpeg (Pinned)")
    
    bin_dir = Path("bin")
    bin_dir.mkdir(exist_ok=True)
    
    ffmpeg_exe = bin_dir / "ffmpeg.exe"
    ffprobe_exe = bin_dir / "ffprobe.exe"
    
    if ffmpeg_exe.exists() and ffprobe_exe.exists():
        print("[OK] Pinned FFmpeg binaries already exist in bin/, skipping download")
        return True

    print(f"Downloading FFmpeg {cfg['version']}...")
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
            print("[FAIL] SHA256 verification FAILED!")
            print(f"Expected: {expected_hash}")
            print(f"Actual:   {actual_hash}")
            return False
        
        print("[OK] SHA256 verification passed.")
        
        # Extract binaries
        print("Extracting binaries...")
        prefix = cfg['strip_prefix']
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.namelist():
                if member.startswith(prefix) and member.endswith(('.exe')):
                    filename = os.path.basename(member)
                    with zip_ref.open(member) as source, open(bin_dir / filename, "wb") as target:
                        shutil.copyfileobj(source, target)
        
        print(f"[OK] Extracted: {ffmpeg_exe.name}, {ffprobe_exe.name}")
        return True
        
    except Exception as e:
        print(f"[FAIL] Failed to download/extract FFmpeg: {e}")
        return False
    finally:
        if zip_path.exists(): zip_path.unlink()
        if sha_path.exists(): sha_path.unlink()

_EMBED_PY_VERSION = "3.12.7"
_EMBED_PY_URL = (
    f"https://www.python.org/ftp/python/{_EMBED_PY_VERSION}/"
    f"python-{_EMBED_PY_VERSION}-embed-amd64.zip"
)
_GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"


def provision_runtime():
    """Download embeddable Python and bootstrap pip into runtime/python/.

    Cached: skipped if runtime/python/python.exe and Lib/site-packages/pip exist.
    """
    print_step("Provisioning bundled Python runtime")
    runtime_dir = Path("runtime") / "python"
    py_exe = runtime_dir / "python.exe"
    pip_pkg = runtime_dir / "Lib" / "site-packages" / "pip"
    setuptools_pkg = runtime_dir / "Lib" / "site-packages" / "setuptools"

    if py_exe.exists() and pip_pkg.exists() and setuptools_pkg.exists():
        print(f"[OK] Bundled runtime already present at {runtime_dir} (cached).")
        return True

    runtime_dir.mkdir(parents=True, exist_ok=True)
    zip_path = Path("runtime") / f"python-{_EMBED_PY_VERSION}-embed.zip"

    try:
        if not zip_path.exists():
            print(f"Downloading {_EMBED_PY_URL} ...")
            urllib.request.urlretrieve(_EMBED_PY_URL, zip_path)
            print("[OK] Downloaded embeddable Python.")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(runtime_dir)
        print(f"[OK] Extracted to {runtime_dir}")

        # Enable site-packages so `pip --target` installs are importable.
        for pth in runtime_dir.glob("python*._pth"):
            text = pth.read_text(encoding="utf-8")
            if "#import site" in text:
                pth.write_text(
                    text.replace("#import site", "import site"), encoding="utf-8"
                )
                print(f"[OK] Enabled site in {pth.name}")

        get_pip = runtime_dir / "get-pip.py"
        print(f"Downloading {_GET_PIP_URL} ...")
        urllib.request.urlretrieve(_GET_PIP_URL, get_pip)
        subprocess.check_call(
            [str(py_exe), str(get_pip), "--no-warn-script-location"]
        )
        print("[OK] pip bootstrapped in bundled runtime.")
        try:
            get_pip.unlink()
        except OSError:
            pass

        # Install setuptools + wheel so PEP 517 sdist builds (e.g. demucs)
        # have a build backend (`setuptools.build_meta`).
        subprocess.check_call([
            str(py_exe), "-m", "pip", "install",
            "--no-warn-script-location",
            "--disable-pip-version-check",
            "setuptools", "wheel",
        ])
        print("[OK] setuptools + wheel installed in bundled runtime.")
        return True
    except Exception as e:
        print(f"[FAIL] Failed to provision bundled runtime: {e}")
        return False


def generate_icon():
    """Render assets/icons/dashboard.svg -> icon.ico via PySide6 + Pillow (no native Cairo needed)."""
    print_step("Generating icon.ico from dashboard.svg")

    if Path("icon.ico").exists():
        print("[OK] icon.ico already exists - skipping generation (delete it to regenerate)")
        return

    helper = Path("_gen_icon.py")
    if not helper.exists():
        print(f"[WARN] {helper} not found - keeping existing icon.ico")
        return

    try:
        subprocess.check_call([sys.executable, str(helper)])
    except subprocess.CalledProcessError as exc:
        print(f"[WARN] Icon generation failed (exit {exc.returncode}) - keeping existing icon.ico")


def ensure_build_venv() -> str:
    """Create/reuse a clean venv with only build requirements. Returns python path."""
    print_step("Preparing Clean Build Venv")
    venv_dir = Path(".build_venv")
    python = venv_dir / "Scripts" / "python.exe"

    if not python.exists():
        print("Creating clean build venv...")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
        print("[OK] Venv created.")
    else:
        print("[OK] Reusing existing build venv.")

    print("Installing build requirements (no AI packages)...")
    subprocess.check_call([
        str(python), "-m", "pip", "install", "--upgrade", "pip", "--quiet",
    ])
    subprocess.check_call([
        str(python), "-m", "pip", "install", "-r", "requirements-build.txt", "--quiet",
    ])
    print("[OK] Build requirements installed.")
    return str(python)


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ (no overwrite)."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def embed_sendgrid_key():
    """Substitute @@SENDGRID_API_KEY@@ in bug_reporter.py with the env value.

    Returns the original file text (or None if no substitution happened) so the
    caller can restore it after PyInstaller finishes.
    """
    _load_env_file(Path(".env"))
    key = (os.environ.get("SENDGRID_API_KEY") or "").strip()
    if not key:
        print("[WARN] SENDGRID_API_KEY not set — bug reporter will fail in built app.")
        return None
    f = Path("gui/tabs/bug_reporter.py")
    original = f.read_text(encoding="utf-8")
    patched = original.replace("@@SENDGRID_API_KEY@@", key)
    if patched == original:
        return None
    f.write_text(patched, encoding="utf-8")
    print("[OK] Embedded SENDGRID_API_KEY into bug_reporter.py")
    return original


def restore_bug_reporter(original: str | None):
    if original is None:
        return
    Path("gui/tabs/bug_reporter.py").write_text(original, encoding="utf-8")
    print("[OK] Restored bug_reporter.py placeholder.")


def build_executable(build_python):
    """Build the executable using PyInstaller"""
    print_step("Building Executable with PyInstaller")

    try:
        # Clean previous builds
        if os.path.exists('dist'):
            shutil.rmtree('dist')
        if os.path.exists('build'):
            shutil.rmtree('build')

        # Build using spec file with clean venv python — no AI packages visible to PyInstaller.
        pi_env = {**os.environ, "VIDEL_PYINSTALLER_BUILD": "1"}
        cmd = [build_python, "-m", "PyInstaller", "media_util_gui.spec", "--clean"]
        # GitHub Actions: capture logs so the job shows the real PyInstaller error (not only exit code).
        if os.environ.get("GITHUB_ACTIONS") == "true":
            proc = subprocess.run(
                cmd,
                env=pi_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if proc.returncode != 0:
                tail = 14000
                out = (proc.stdout or "").strip()
                err = (proc.stderr or "").strip()
                print("[FAIL] PyInstaller exited with code", proc.returncode)
                if out:
                    print("[FAIL] stdout (tail):\n", out[-tail:])
                if err:
                    print("[FAIL] stderr (tail):\n", err[-tail:])
                return False
        else:
            subprocess.check_call(cmd, env=pi_env)

        print("[OK] Executable built successfully!")
        return True

    except subprocess.CalledProcessError as e:
        print(f"[FAIL] Failed to build executable: {e}")
        return False

def compile_installer(version):
    """Compile Inno Setup installer"""
    print_step("Compiling Inno Setup Installer")
    
    iscc = shutil.which('iscc') or r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
    if not os.path.exists(iscc):
        print(f"[WARN] ISCC.exe not found at {iscc}. Please install Inno Setup 6.")
        print("Skipping installer compilation.")
        return True # Don't fail the whole build if just installer fails due to missing tool
        
    try:
        subprocess.check_call([iscc, f'/DAppVersion={version}', 'installer.iss'])
        print("[OK] Installer compiled successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[FAIL] Failed to compile installer: {e}")
        return False

def measure_sizes(dist_dir, installer_path):
    """Measure sizes of installed files and installer"""
    print_step("Measuring Sizes")
    
    dist_path = Path(dist_dir)
    if not dist_path.exists():
        print(f"[WARN] {dist_dir} not found, skipping measurements.")
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

def evaluate_budget(installer_mb, installed_mb):
    """Return (verdict, failures[]) given size-budget.json. Seeds file if missing."""
    budget_file = Path('size-budget.json')

    if not budget_file.exists():
        print_step("Seeding Size Budget")
        budget = {
            "installer_mb": round(installer_mb, 1),
            "installed_mb": round(installed_mb, 1),
            "tolerance_pct": 5,
        }
        with open(budget_file, 'w') as f:
            json.dump(budget, f, indent=2)
        print(f"[OK] Seeded {budget_file} with current measurements.")
        print("[WARN] Commit this file to enforce these limits in future builds.")
        return "pass", []

    with open(budget_file) as f:
        budget = json.load(f)

    tol = 1 + budget.get('tolerance_pct', 5) / 100
    failures = []
    if installer_mb > budget['installer_mb'] * tol:
        failures.append(f"Installer {installer_mb:.1f} MB > budget {budget['installer_mb']} MB (x{tol})")
    if installed_mb > budget['installed_mb'] * tol:
        failures.append(f"Installed {installed_mb:.1f} MB > budget {budget['installed_mb']} MB (x{tol})")

    return ("fail" if failures else "pass"), failures


def write_size_report(installer_mb, installed_mb, top10, verdict):
    """Write build artifact dist/size-report.json (per data-model schema)."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "installer_mb": installer_mb,
        "installed_mb": installed_mb,
        "budget_verdict": verdict,
        "top_contributors": [{"path": str(p), "mb": round(mb, 3)} for p, mb in top10],
    }
    Path('dist').mkdir(exist_ok=True)
    report_path = Path('dist/size-report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"[OK] Size report written to {report_path}")


def enforce_budget(verdict, failures, top10):
    """Print top-10 contributors to stderr and exit non-zero on overrun."""
    if verdict == "pass":
        print("[OK] Size budget check passed.")
        return
    print("\n[FAIL] BUILD FAILED - size budget exceeded:", file=sys.stderr)
    for msg in failures:
        print(f"  {msg}", file=sys.stderr)
    print("\nTop 10 contributors:", file=sys.stderr)
    for p, mb in top10:
        print(f"  {mb:6.2f} MB  {p}", file=sys.stderr)
    sys.exit(1)


EXCLUDED_AI_PACKAGES = {"rembg", "demucs", "torch", "tensorflow", "cv2", "numba", "onnxruntime"}


def run_exclude_test(build_python):
    """Run tests/test_build_excludes.py against dist/Videl/. Fail build on leak."""
    print_step("Verifying Build Excludes")
    test_path = Path("tests/test_build_excludes.py")
    if not test_path.exists():
        print(f"[WARN] {test_path} not found; skipping.")
        return
    try:
        subprocess.check_call([build_python, "-m", "pytest", str(test_path), "-v"])
        print("[OK] No excluded AI packages leaked into dist/Videl/.")
    except subprocess.CalledProcessError as e:
        print(f"[FAIL] Excluded AI packages leaked into dist/Videl/ (pytest exit {e.returncode})", file=sys.stderr)
        sys.exit(1)

def main():
    """Main build process"""
    print("Videl - Windows Build Pipeline")
    print("=" * 60)
    
    if sys.platform != "win32":
        print("[FAIL] This build pipeline requires Windows.")
        sys.exit(1)
    
    config = load_build_config()
    version = get_app_version()
    
    # Step 2: Download ffmpeg
    if not download_ffmpeg_pinned(config['ffmpeg']):
        sys.exit(1)

    # Step 3: Regenerate icon from in-app dashboard.svg
    generate_icon()

    # Step 3b: Provision bundled embeddable Python (cached on rebuild).
    if not provision_runtime():
        sys.exit(1)

    # Step 4: PyInstaller (embed SendGrid key first; restore source after build).
    build_python = ensure_build_venv()
    _bug_reporter_backup = embed_sendgrid_key()
    try:
        if not build_executable(build_python):
            sys.exit(1)
    finally:
        restore_bug_reporter(_bug_reporter_backup)

    # Step 4b: Verify excludes (no AI packages leaked into dist/Videl/)
    run_exclude_test(build_python)

    # Step 5: Inno Setup
    if not compile_installer(version):
        sys.exit(1)

    # Step 6: Measure
    installer_path = "Output/Videl_Setup.exe"
    if not os.path.exists(installer_path):
        if os.path.exists("installer/Videl_Setup.exe"):
            installer_path = "installer/Videl_Setup.exe"

    installer_mb, installed_mb, top10 = measure_sizes("dist/Videl", installer_path)

    # Step 7: Evaluate budget then write report (always) then enforce exit
    verdict, failures = evaluate_budget(installer_mb, installed_mb)
    write_size_report(installer_mb, installed_mb, top10, verdict)
    enforce_budget(verdict, failures, top10)
    
    print("\nBuild complete.")
    print(f"Installer: {os.path.abspath(installer_path)}")

if __name__ == "__main__":
    main()
