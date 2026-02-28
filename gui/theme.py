import threading
import darkdetect
import ttkbootstrap as ttk

class ThemeManager:
    """Manages application theme state and OS detection."""
    
    def __init__(self, root):
        self.root = root
        self.mode = "auto"  # auto, light, dark
        self.light_theme = "cosmo"
        self.dark_theme = "darkly"
        
    def initialize(self):
        """Applies initial theme and starts listener."""
        self._apply_theme()
        
        # Start a listener for OS theme changes in a daemon thread
        threading.Thread(target=self._os_theme_listener, daemon=True).start()

    def set_mode(self, mode: str):
        self.mode = mode
        self._apply_theme()

    def _apply_theme(self):
        """Applies the current theme based on mode and OS preference."""
        theme_name = self.get_current_theme_name()
        ttk.Style().theme_use(theme_name)

    def get_current_theme_name(self):
        """Returns the active ttkbootstrap theme name."""
        if self.mode == "auto":
            is_dark = darkdetect.isDark()
            return self.dark_theme if is_dark else self.light_theme
        return self.dark_theme if self.mode == "dark" else self.light_theme

    def toggle(self):
        """Cycles theme: auto -> light -> dark -> auto. Applies immediately and returns mode."""
        if self.mode == "auto":
            self.mode = "light"
        elif self.mode == "light":
            self.mode = "dark"
        else:
            self.mode = "auto"
            
        self._apply_theme()
        return self.mode

    def get_current_mode(self):
        """Returns current mode: 'auto', 'light', or 'dark'."""
        return self.mode

    def _os_theme_listener(self):
        """Listens for OS theme changes and updates the GUI if in 'auto' mode."""
        import time
        last_theme = darkdetect.isDark()
        while True:
            time.sleep(2)
            if self.mode == "auto":
                current_theme = darkdetect.isDark()
                if current_theme != last_theme:
                    last_theme = current_theme
                    # Dispatch to main thread
                    self.root.after(0, self._apply_theme)
