from PySide6.QtCore import QThread, Signal, QObject
import traceback

class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.
    """
    finished = Signal()
    error = Signal(tuple)
    result = Signal(object)
    progress = Signal(int, int, str)
    intercept_status = Signal(str)

class Worker(QThread):
    """
    Worker thread for executing background tasks without blocking the UI.
    Supports basic cancellation if the running function periodically checks an injected callback.
    """
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.is_cancelled = False

    def run(self):
        """
        Execute the function and emit signals.
        """
        try:
            result = self.fn(*self.args, **self.kwargs)
            if not self.is_cancelled:
                self.signals.result.emit(result)
        except Exception as e:
            if not self.is_cancelled:
                self.signals.error.emit((type(e), str(e), traceback.format_exc()))
        finally:
            self.signals.finished.emit()

    def cancel(self):
        """Request the worker to stop."""
        self.is_cancelled = True
        
    def check_cancelled(self) -> bool:
        """Can be passed to long running logic to check for cancellation."""
        return self.is_cancelled
