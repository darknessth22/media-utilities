#!/usr/bin/env python3
"""
Build script for creating Windows executable and installer for Media Utility GUI
"""

import os
import sys
import subprocess
import urllib.request
import zipfile
import shutil
from pathlib import Path

def print_step(step_name):
    """Print a formatted step header"""
    print(f"\n{'='*60}")
    print(f"STEP: {step_name}")
    print(f"{'='*60}")

def download_ffmpeg():
    """Download FFmpeg for Windows if not present"""
    print_step("Downloading FFmpeg")

    if os.path.exists('ffmpeg.exe'):
        print("✅ FFmpeg already exists, skipping download")
        return True

    # Check if we're in WSL2
    is_wsl = os.path.exists('/proc/version') and 'microsoft' in open('/proc/version').read().lower()

    if is_wsl:
        print("� Detected WSL2 environment")
        print("�📥 Downloading FFmpeg for Windows...")
    else:
        print("🪟 Detected Windows environment")
        print("📥 Downloading FFmpeg for Windows...")

    # FFmpeg download URL (using a reliable source)
    ffmpeg_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

    try:
        print("Downloading FFmpeg archive...")
        urllib.request.urlretrieve(ffmpeg_url, "ffmpeg.zip")

        print("Extracting FFmpeg...")
        with zipfile.ZipFile("ffmpeg.zip", 'r') as zip_ref:
            zip_ref.extractall("ffmpeg_temp")

        # Find the ffmpeg.exe in the extracted files
        for root, dirs, files in os.walk("ffmpeg_temp"):
            if "ffmpeg.exe" in files:
                shutil.copy2(os.path.join(root, "ffmpeg.exe"), "ffmpeg.exe")
                break

        # Cleanup
        os.remove("ffmpeg.zip")
        shutil.rmtree("ffmpeg_temp")

        print("✅ FFmpeg downloaded successfully!")
        return True

    except Exception as e:
        print(f"❌ Failed to download FFmpeg: {e}")
        print("Please download FFmpeg manually from https://ffmpeg.org/download.html")
        return False

def install_dependencies():
    """Install required dependencies"""
    print_step("Installing Dependencies")
    
    try:
        print("📦 Installing Python dependencies...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Dependencies installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

def create_icon():
    """Create a simple icon file if none exists"""
    print_step("Creating Application Icon")
    
    if os.path.exists('icon.ico'):
        print("✅ Icon already exists, skipping creation")
        return True
    
    try:
        from PIL import Image, ImageDraw
        
        # Create a simple icon
        size = (256, 256)
        image = Image.new('RGBA', size, (70, 130, 180, 255))  # Steel blue background
        draw = ImageDraw.Draw(image)
        
        # Draw a simple media play symbol
        triangle_points = [(80, 60), (80, 196), (196, 128)]
        draw.polygon(triangle_points, fill=(255, 255, 255, 255))
        
        # Save as ICO
        image.save('icon.ico', format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
        print("✅ Icon created successfully!")
        return True
        
    except Exception as e:
        print(f"⚠️ Could not create icon: {e}")
        print("Continuing without icon...")
        return True

def build_executable():
    """Build the executable using PyInstaller"""
    print_step("Building Executable")
    
    try:
        print("🔨 Building executable with PyInstaller...")
        
        # Clean previous builds
        if os.path.exists('dist'):
            shutil.rmtree('dist')
        if os.path.exists('build'):
            shutil.rmtree('build')
        
        # Build using spec file
        subprocess.check_call([sys.executable, "-m", "PyInstaller", "media_util_gui.spec", "--clean"])
        
        print("✅ Executable built successfully!")
        print(f"📁 Executable location: {os.path.abspath('dist/MediaUtility.exe')}")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to build executable: {e}")
        return False

def create_installer_script():
    """Create Inno Setup script for Windows installer"""
    print_step("Creating Installer Script")
    
    installer_script = '''
[Setup]
AppName=Media Utility
AppVersion=1.0
AppPublisher=Media Utility Developer
AppPublisherURL=https://github.com/yourusername/media-utility
DefaultDirName={autopf}\\MediaUtility
DefaultGroupName=Media Utility
OutputDir=installer
OutputBaseFilename=MediaUtility_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\\MediaUtility.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\\MediaUtility.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\\Media Utility"; Filename: "{app}\\MediaUtility.exe"
Name: "{group}\\{cm:UninstallProgram,Media Utility}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\\Media Utility"; Filename: "{app}\\MediaUtility.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\\MediaUtility.exe"; Description: "{cm:LaunchProgram,Media Utility}"; Flags: nowait postinstall skipifsilent
'''
    
    try:
        with open('media_utility_installer.iss', 'w') as f:
            f.write(installer_script.strip())
        
        print("✅ Installer script created: media_utility_installer.iss")
        print("\n📋 To create the installer:")
        print("1. Install Inno Setup from: https://jrsoftware.org/isinfo.php")
        print("2. Open media_utility_installer.iss with Inno Setup")
        print("3. Click 'Build' -> 'Compile' to create the installer")
        print("4. The installer will be created in the 'installer' folder")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to create installer script: {e}")
        return False

def main():
    """Main build process"""
    print("🚀 Media Utility - Windows Executable Builder")
    print("=" * 60)
    
    # Check if we're on Windows
    if sys.platform != "win32":
        print("⚠️ This script is designed for Windows. Some features may not work on other platforms.")
    
    steps = [
        ("Download FFmpeg", download_ffmpeg),
        ("Install Dependencies", install_dependencies),
        ("Create Icon", create_icon),
        ("Build Executable", build_executable),
        ("Create Installer Script", create_installer_script)
    ]
    
    failed_steps = []
    
    for step_name, step_func in steps:
        if not step_func():
            failed_steps.append(step_name)
    
    print_step("Build Summary")
    
    if not failed_steps:
        print("🎉 All steps completed successfully!")
        print("\n📁 Files created:")
        print(f"   - Executable: {os.path.abspath('dist/MediaUtility.exe')}")
        print(f"   - Installer Script: {os.path.abspath('media_utility_installer.iss')}")
        
        print("\n🎯 Next Steps:")
        print("1. Test the executable: dist/MediaUtility.exe")
        print("2. Install Inno Setup to create the installer")
        print("3. Compile media_utility_installer.iss to create the installer package")
        
    else:
        print(f"⚠️ Build completed with {len(failed_steps)} failed step(s):")
        for step in failed_steps:
            print(f"   - {step}")
        print("\nPlease resolve the issues and run the script again.")

if __name__ == "__main__":
    main()
