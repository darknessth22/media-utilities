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

def test_download_token_signal_guard(download_section):
    """Verify that stale signal callbacks are discarded."""
    download_section._url_input.text.return_value = "https://youtube.com/watch?v=123"
    download_section._audio_radio.isChecked.return_value = False
    
    with patch('gui.tabs.download_section.Worker') as MockWorker, \
         patch('gui.tabs.download_section.download_media'):
        
        # Ensure different workers for each call
        worker1 = MagicMock()
        worker2 = MagicMock()
        MockWorker.side_effect = [worker1, worker2]
        
        # Start first download
        download_section.trigger_primary_action()
        token1 = download_section._download_token
        
        # Start second download (simulated)
        download_section._worker = None # Simulate first worker finished or cancelled
        download_section.trigger_primary_action()
        token2 = download_section._download_token
        
        assert token2 > token1
        
        # Mock _on_result to see if it's called
        download_section._on_result = MagicMock()
        
        # Trigger result signal from first worker (stale token)
        # In implementation, the lambda closure captures the token
        # We need to find the lambda connected to the signal
        args, kwargs = worker1.signals.result.connect.call_args
        callback1 = args[0]
        
        callback1({"success": True, "file_path": "stale.mp4"})
        download_section._on_result.assert_not_called()
        
        # Trigger result signal from second worker (current token)
        args, kwargs = worker2.signals.result.connect.call_args
        callback2 = args[0]
        
        callback2({"success": True, "file_path": "current.mp4"})
        download_section._on_result.assert_called_once()
