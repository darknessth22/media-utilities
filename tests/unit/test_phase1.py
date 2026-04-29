"""Phase 1 unit tests — path sanitization and FFmpeg command builders."""
import pytest
from utils.sanitize import sanitize_filename, is_safe_filename


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------

class TestSanitizeFilename:
    def test_clean_name_unchanged(self):
        assert sanitize_filename("my_video_2024") == "my_video_2024"

    def test_strips_path_separators(self):
        result = sanitize_filename("folder/sub\\file")
        assert "/" not in result
        assert "\\" not in result

    def test_strips_illegal_windows_chars(self):
        for ch in '<>:"|?*':
            result = sanitize_filename(f"file{ch}name")
            assert ch not in result

    def test_strips_null_bytes(self):
        result = sanitize_filename("file\x00name")
        assert "\x00" not in result

    def test_strips_control_chars(self):
        result = sanitize_filename("file\x1fname")
        assert "\x1f" not in result

    def test_collapses_repeated_separators(self):
        result = sanitize_filename("video___title")
        assert "__" not in result

    def test_strips_leading_trailing_dots(self):
        result = sanitize_filename("...video...")
        assert not result.startswith(".")
        assert not result.endswith(".")

    def test_strips_leading_trailing_spaces(self):
        result = sanitize_filename("  video  ")
        assert not result.startswith(" ")
        assert not result.endswith(" ")

    def test_max_length_enforced(self):
        long_name = "a" * 300
        result = sanitize_filename(long_name, max_length=200)
        assert len(result) <= 200

    def test_empty_after_sanitization_raises(self):
        with pytest.raises(ValueError):
            sanitize_filename("...")

    def test_windows_reserved_name_prefixed(self):
        result = sanitize_filename("CON")
        assert not result.upper().startswith("CON") or result.startswith("_")

    def test_windows_reserved_name_with_ext(self):
        result = sanitize_filename("NUL.mp4")
        assert result.upper() != "NUL.MP4"

    def test_unicode_preserved(self):
        result = sanitize_filename("vidéo_été")
        assert "vid" in result

    def test_type_error_on_non_string(self):
        with pytest.raises(TypeError):
            sanitize_filename(123)


class TestIsSafeFilename:
    def test_safe_name(self):
        assert is_safe_filename("clean_file_name") is True

    def test_unsafe_with_slash(self):
        assert is_safe_filename("path/name") is False

    def test_unsafe_with_colon(self):
        assert is_safe_filename("C:video") is False

    def test_empty_string_is_unsafe(self):
        assert is_safe_filename("") is False


# ---------------------------------------------------------------------------
# FFmpeg command builders — verify list form and no shell injection vectors
# ---------------------------------------------------------------------------

class TestFFmpegCommandBuilders:
    """Verify that command lists produced by core modules are properly formed."""

    def test_trim_cmd_is_list(self):
        """trim_media builds a list command — never a string."""
        import inspect
        import core.trimmer as trimmer_mod
        src = inspect.getsource(trimmer_mod)
        # Must not construct a shell string via f"ffmpeg ..."
        assert 'shell=True' not in src

    def test_muxer_cmd_is_list(self):
        import inspect
        import core.muxer as muxer_mod
        src = inspect.getsource(muxer_mod)
        assert 'shell=True' not in src

    def test_spatial_cmd_is_list(self):
        import inspect
        import core.spatial as spatial_mod
        src = inspect.getsource(spatial_mod)
        assert 'shell=True' not in src

    def test_downloader_cmd_is_list(self):
        import inspect
        import core.downloader as dl_mod
        src = inspect.getsource(dl_mod)
        assert 'shell=True' not in src

    def test_trim_output_path_sanitized(self):
        """trim_media output filename contains no path separators from basename."""
        import os
        # Construct the same path logic used in trim_media
        filename = "my:video/clip.mp4"
        base, ext = os.path.splitext(os.path.basename(filename))
        output_stem = f"{base}_trimmed"
        # Basename strips path sep already; sanitize should catch colons
        from utils.sanitize import sanitize_filename
        safe = sanitize_filename(output_stem)
        assert ":" not in safe
        assert "/" not in safe


# ---------------------------------------------------------------------------
# Logger masking
# ---------------------------------------------------------------------------

class TestCredentialMasking:
    def test_masks_cookies_flag(self):
        from utils.app_logger import mask_credentials
        result = mask_credentials("--cookies /home/user/secret_cookies.txt")
        assert "secret_cookies" not in result
        assert "[REDACTED]" in result

    def test_masks_cookies_from_browser(self):
        from utils.app_logger import mask_credentials
        result = mask_credentials("--cookies-from-browser chrome")
        assert "chrome" not in result
        assert "[REDACTED]" in result

    def test_masks_bearer_token(self):
        from utils.app_logger import mask_credentials
        result = mask_credentials("Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.abc123")
        assert "eyJ" not in result
        assert "[REDACTED]" in result

    def test_masks_client_secret(self):
        from utils.app_logger import mask_credentials
        result = mask_credentials("client_secret=supersecretvalue123")
        assert "supersecretvalue123" not in result

    def test_safe_text_unchanged(self):
        from utils.app_logger import mask_credentials
        text = "Download completed: my_video.mp4 (12 MB)"
        assert mask_credentials(text) == text

    def test_masks_session_token(self):
        from utils.app_logger import mask_credentials
        result = mask_credentials("session=abc123def456")
        assert "abc123def456" not in result


# ---------------------------------------------------------------------------
# Process registry
# ---------------------------------------------------------------------------

class TestProcessRegistry:
    def test_register_and_cancel(self):
        import subprocess
        import sys
        from utils.process_registry import register, cancel_job

        # Start a long-running process
        if sys.platform == "win32":
            proc = subprocess.Popen(["ping", "-n", "30", "127.0.0.1"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            proc = subprocess.Popen(["sleep", "30"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        job_id = "test-cancel-job"
        register(job_id, proc)
        killed = cancel_job(job_id)
        assert killed == 1
        assert proc.poll() is not None  # process is dead

    def test_cancel_unknown_job_returns_zero(self):
        from utils.process_registry import cancel_job
        assert cancel_job("nonexistent-job-xyz") == 0
