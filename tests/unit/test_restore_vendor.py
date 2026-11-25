"""Photo Restore's child process loads the RestoreFormer++ arch by path."""
import os

from core.paths import resource_path


def test_restoreformer_arch_is_where_restore_passes_it():
    path = resource_path("core", "vendor", "restoreformer_arch.py")
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as f:
        assert "class VQVAEGANMultiHeadTransformer" in f.read()


def test_spec_bundles_vendor_dir():
    with open(resource_path("media_util_gui.spec"), encoding="utf-8") as f:
        assert "('core/vendor', 'core/vendor')" in f.read()
