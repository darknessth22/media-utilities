# Media Utility - Windows Executable Build Instructions

This guide will help you create a Windows executable (.exe) and installation package for the Media Utility GUI application.

## Prerequisites

### Required Software
1. **Python 3.8+** - Download from [python.org](https://python.org)
2. **Git** (optional) - For cloning the repository
3. **Inno Setup** (for installer) - Download from [jrsoftware.org](https://jrsoftware.org/isinfo.php)

### System Requirements
- Windows 10/11 (64-bit recommended)
- At least 2GB free disk space
- Internet connection (for downloading dependencies)

## Quick Start

### Option 1: Automated Build (Recommended)
1. Open Command Prompt or PowerShell as Administrator
2. Navigate to the project directory
3. Run the build script:
   ```batch
   build.bat
   ```

### Option 2: Manual Build
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the build script:
   ```bash
   python build_executable.py
   ```

## Build Process Steps

The build script performs these steps automatically:

### 1. Download FFmpeg
- Downloads FFmpeg for Windows automatically
- Places `ffmpeg.exe` in the project directory
- Required for media processing functionality

### 2. Install Dependencies
- Installs all Python packages from `requirements.txt`
- Includes PyInstaller for creating the executable

### 3. Create Application Icon
- Generates a simple icon file (`icon.ico`)
- You can replace this with your custom icon

### 4. Build Executable
- Uses PyInstaller to create a standalone executable
- Bundles all dependencies into a single file
- Output: `dist/MediaUtility.exe`

### 5. Create Installer Script
- Generates Inno Setup script (`media_utility_installer.iss`)
- Ready to compile into a Windows installer

## Creating the Installation Package

After the build script completes:

1. **Install Inno Setup** from [jrsoftware.org](https://jrsoftware.org/isinfo.php)

2. **Open the installer script**:
   - Launch Inno Setup
   - Open `media_utility_installer.iss`

3. **Compile the installer**:
   - Click `Build` → `Compile`
   - The installer will be created in the `installer` folder
   - Output: `installer/MediaUtility_Setup.exe`

## File Structure After Build

```
project/
├── dist/
│   └── MediaUtility.exe          # Standalone executable
├── installer/
│   └── MediaUtility_Setup.exe    # Windows installer
├── build/                        # Build artifacts (can be deleted)
├── media_utility_installer.iss   # Inno Setup script
├── icon.ico                      # Application icon
├── ffmpeg.exe                    # FFmpeg executable
└── ...
```

## Testing the Executable

1. **Test the standalone executable**:
   ```bash
   dist/MediaUtility.exe
   ```

2. **Test the installer**:
   - Run `installer/MediaUtility_Setup.exe`
   - Follow the installation wizard
   - Launch from Start Menu or Desktop shortcut

## Troubleshooting

### Common Issues

**"FFmpeg not found" error:**
- Ensure `ffmpeg.exe` is in the same directory as the executable
- The build script should handle this automatically

**"Module not found" error:**
- Some dependencies might not be detected automatically
- Add missing modules to `hiddenimports` in `media_util_gui.spec`

**Large executable size:**
- The executable includes all dependencies (~100-200MB is normal)
- This ensures it runs on any Windows PC without additional installations

**Antivirus false positives:**
- Some antivirus software may flag PyInstaller executables
- This is a known issue with PyInstaller
- You may need to add exceptions or sign the executable

### Manual FFmpeg Installation

If automatic download fails:

1. Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html)
2. Extract the archive
3. Copy `ffmpeg.exe` to your project directory
4. Re-run the build script

### Custom Icon

To use your own icon:

1. Create or obtain an `.ico` file
2. Name it `icon.ico`
3. Place it in the project directory
4. Re-run the build script

## Distribution

### Standalone Executable
- Share `dist/MediaUtility.exe`
- Recipients need no additional software
- Larger file size (~100-200MB)

### Installation Package
- Share `installer/MediaUtility_Setup.exe`
- Professional installation experience
- Creates Start Menu and Desktop shortcuts
- Includes uninstaller

## Advanced Configuration

### Customizing the Build

Edit `media_util_gui.spec` to:
- Add additional data files
- Modify hidden imports
- Change executable name or icon
- Adjust build options

### Customizing the Installer

Edit `media_utility_installer.iss` to:
- Change installation directory
- Modify shortcuts and icons
- Add license agreement
- Include additional files

## Security Considerations

- The executable is not code-signed by default
- Consider code signing for distribution to avoid security warnings
- Test thoroughly on clean Windows systems
- Scan with antivirus before distribution

## Support

If you encounter issues:

1. Check the console output for error messages
2. Ensure all prerequisites are installed
3. Try running individual steps manually
4. Check PyInstaller documentation for advanced troubleshooting

---

**Note**: This build process creates a portable application that can run on any Windows PC without requiring Python or additional dependencies to be installed.
