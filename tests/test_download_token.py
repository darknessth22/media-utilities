import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication
from gui.tabs.download_section import DownloadSection

# Need a QApplication for QWidget-based tests
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.output_folder = ""
    settings.default_codec = "original"
    return settings

@pytest.fixture
def download_section(qapp, mock_settings):
    with patch('gui.tabs.download_section._MULTIMEDIA_AVAILABLE', False):
        section = DownloadSection(mock_settings)
        # Mock widgets that might be accessed
        section._url_input = MagicMock()
        section._progress_bar = MagicMock()
        section._progress_label = MagicMock()
        section._speed_label = MagicMock()
        section._eta_label = MagicMock()
        section._quality_combo = MagicMock()
        section._quality_combo.currentIndex.return_value = 0
        section._audio_radio = MagicMock()
        section._start_input = MagicMock()
        section._end_input = MagicMock()
        section._out_input = MagicMock()
        return section


def test_stale_job_result_signal_guard(download_section):
    """A result for a job that is no longer active must not clear the current worker."""
    active_worker = MagicMock()
    download_section._worker = active_worker
    download_section._active_job = {
        "job_id": "job-b",
        "url": "https://example.com/b",
        "display_name": "b",
        "status": "downloading",
        "platform": "youtube",
        "media_type": "video",
        "quality": None,
        "audio_fmt": "mp3",
        "video_audio_fmt": "Original",
        "start_time": None,
        "end_time": None,
        "out_dir": None,
        "video_codec": "original",
        "playlist_mode": "single",
    }
    download_section._on_job_result("job-a", {"success": True, "file_path": "stale.mp4"})
    assert download_section._worker is active_worker
    assert download_section._active_job["job_id"] == "job-b"


def test_stale_job_error_signal_guard(download_section):
    """An error for a non-active job must not clear the current worker."""
    active_worker = MagicMock()
    download_section._worker = active_worker
    download_section._active_job = {"job_id": "x", "url": "u", "display_name": "x", "status": "downloading"}
    download_section._on_job_error("y", (RuntimeError, "boom", ""))
    assert download_section._worker is active_worker
    assert download_section._active_job["job_id"] == "x"
