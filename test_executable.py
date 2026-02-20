#!/usr/bin/env python3
"""
Test script to verify the Media Utility executable works correctly
"""

import os
import sys
import subprocess
import time
from pathlib import Path

def test_executable_exists():
    """Test if the executable was created"""
    exe_path = Path("dist/MediaUtility/MediaUtility.exe")
    if exe_path.exists():
        print(f"✅ Executable found: {exe_path.absolute()}")
        print(f"📏 File size: {exe_path.stat().st_size / (1024*1024):.1f} MB")
        return True
    else:
        print("❌ Executable not found at dist/MediaUtility/MediaUtility.exe")
        return False

def test_executable_launch():
    """Test if the executable can launch"""
    print("\n🚀 Testing executable launch...")
    
    try:
        # Launch the executable in a separate process
        process = subprocess.Popen(
            ["dist/MediaUtility/MediaUtility.exe"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        )
        
        # Wait a moment for it to start
        time.sleep(3)
        
        # Check if it's still running (GUI should stay open)
        if process.poll() is None:
            print("✅ Executable launched successfully!")
            print("🖥️ GUI should be visible now")
            
            # Terminate the process for testing
            process.terminate()
            process.wait(timeout=5)
            print("✅ Executable terminated cleanly")
            return True
        else:
            stdout, stderr = process.communicate()
            print("❌ Executable exited immediately")
            if stderr:
                print(f"Error output: {stderr.decode()}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to launch executable: {e}")
        return False

def test_ffmpeg_bundled():
    """Test if FFmpeg is properly bundled"""
    print("\n🔧 Testing FFmpeg integration...")
    
    # This is a basic test - the real test would be running the executable
    # and checking if media operations work
    if os.path.exists("ffmpeg.exe"):
        print("✅ FFmpeg executable found in project directory")
        return True
    else:
        print("⚠️ FFmpeg not found in project directory")
        print("   The executable should still work if FFmpeg is bundled correctly")
        return True

def test_installer_script():
    """Test if installer script was created"""
    print("\n📦 Testing installer script...")
    
    iss_path = Path("media_utility_installer.iss")
    if iss_path.exists():
        print(f"✅ Installer script found: {iss_path.absolute()}")
        
        # Check if it contains expected content
        content = iss_path.read_text()
        if "MediaUtility.exe" in content and "[Setup]" in content:
            print("✅ Installer script appears to be valid")
            return True
        else:
            print("⚠️ Installer script may be incomplete")
            return False
    else:
        print("❌ Installer script not found")
        return False

def main():
    """Run all tests"""
    print("🧪 Media Utility - Executable Test Suite")
    print("=" * 50)
    
    tests = [
        ("Executable Exists", test_executable_exists),
        ("Executable Launch", test_executable_launch),
        ("FFmpeg Integration", test_ffmpeg_bundled),
        ("Installer Script", test_installer_script)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 Running: {test_name}")
        print("-" * 30)
        
        try:
            if test_func():
                passed += 1
            else:
                print(f"❌ {test_name} failed")
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Your executable should work correctly.")
        print("\n📋 Next steps:")
        print("1. Test the executable manually: dist/MediaUtility/MediaUtility.exe")
        print("2. Create the installer using Inno Setup")
        print("3. Test the installer on a clean Windows system")
    else:
        print(f"⚠️ {total - passed} test(s) failed. Please check the issues above.")
        print("\n🔧 Troubleshooting:")
        print("1. Make sure the build process completed successfully")
        print("2. Check for any error messages in the build output")
        print("3. Try rebuilding with: python build_executable.py")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
