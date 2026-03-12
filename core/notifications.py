import asyncio
import threading
from desktop_notifier import DesktopNotifier, Notification

class NotificationDispatcher:
    def __init__(self, app_name="Media Utilities"):
        self._app_name = app_name
        self.notifier = None
        self.loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self.thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.thread.start()
        self._ready.wait()  # Block until notifier is created on the correct thread

    def _run_event_loop(self):
        # Initialize the WinRT STA COM apartment on this thread before any WinRT calls.
        # Without this, COM objects created here cannot be accessed from other threads.
        try:
            from winrt._winrt import init_apartment, STA
            init_apartment(STA)
        except Exception:
            pass

        asyncio.set_event_loop(self.loop)
        # Create the notifier on this thread so all COM object affinity is correct.
        self.notifier = DesktopNotifier(app_name=self._app_name)
        self._ready.set()
        self.loop.run_forever()

    def send_notification(self, title, message, on_clicked=None):
        """
        Send a native OS notification.
        :param title: The title of the notification.
        :param message: The message body.
        :param on_clicked: Optional callback function when notification is clicked.
        """
        asyncio.run_coroutine_threadsafe(
            self._async_send(title, message, on_clicked),
            self.loop
        )

    async def _async_send(self, title, message, on_clicked):
        n = Notification(
            title=title,
            message=message,
            on_clicked=on_clicked
        )
        await self.notifier.send_notification(n)

# Global instance
_dispatcher = None

def get_notifier():
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = NotificationDispatcher()
    return _dispatcher
