"""Runtime hook — make pip._vendor packages importable inside the frozen exe.

pip's `_vendor` namespace uses a custom MetaPathFinder (`VendorImporter`) that
expects to find vendored packages at a specific filesystem path. PyInstaller
flattens the layout, so we manually register the vendored modules as aliases
of the real top-level pip._vendor.<name> packages once they exist on sys.path.
"""
import sys


def _alias_pip_vendor():
    try:
        import pip._vendor  # noqa: F401
    except Exception:
        return
    # The VendorImporter expects modules at pip._vendor.<name>; PyInstaller
    # already places them there, but the finder may not be registered.
    import pip._vendor as _v
    # Force submodule discovery — collect_all should have packed them.
    for name in ("distlib", "packaging", "pkg_resources", "platformdirs",
                 "pyparsing", "pyproject_hooks", "requests", "resolvelib",
                 "rich", "tomli", "truststore", "urllib3"):
        try:
            __import__(f"pip._vendor.{name}")
        except Exception:
            pass


_alias_pip_vendor()
