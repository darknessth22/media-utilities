import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Callable
from core.settings import UserSettings

SETTINGS_SECTIONS = [
    {
        "name": "Output",
        "fields": [
            {
                "key": "output_folder",
                "label": "Default Output Folder",
                "type": "folder_picker",
                "description": "Where to save converted/trimmed files by default",
            }
        ],
    },
    {
        "name": "Video",
        "fields": [
            {
                "key": "default_codec",
                "label": "Default Video Codec",
                "type": "dropdown",
                "options": [
                    ("Original (no re-encoding)", "original"),
                    ("H.264 (most compatible)", "h264"),
                    ("HEVC/H.265 (smaller files)", "hevc"),
                    ("VP9 (open source)", "vp9"),
                ],
                "description": "Codec to use when converting videos",
            }
        ],
    },
    {
        "name": "Appearance",
        "fields": [
            {
                "key": "theme_mode",
                "label": "Theme",
                "type": "dropdown",
                "options": [
                    ("Follow System", "auto"),
                    ("Light", "light"),
                    ("Dark", "dark"),
                ],
                "description": "Application color theme",
            }
        ],
    },
]

OnSettingsChanged = Callable[[UserSettings], None]

class SettingsPanel(tk.Toplevel):
    def __init__(self, parent: tk.Widget, current_settings: UserSettings, on_settings_changed: OnSettingsChanged):
        super().__init__(parent)
        self.parent = parent
        self.current_settings = current_settings
        self.on_settings_changed = on_settings_changed
        
        self.title("Settings")
        self.geometry("500x400")
        self.resizable(False, False)
        
        # Initialize UI variables from current settings
        self.vars = {
            "output_folder": tk.StringVar(value=self.current_settings.output_folder or ""),
            "default_codec": tk.StringVar(value=self.current_settings.default_codec),
            "theme_mode": tk.StringVar(value=self.current_settings.theme_mode)
        }
        
        self._comboboxes = []
        
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.hide)
        
    def destroy(self):
        try:
            from ttkbootstrap.publisher import Publisher
            # The style.py assigns combobox popdown updates bound to the widget name
            # Publisher.__subscribers is a dict mapping widget_name -> Subscriber
            for combo in getattr(self, '_comboboxes', []):
                # We need to unsubscribe using the widget's tcl string name
                c_name = str(combo)
                Publisher.unsubscribe(c_name)
        except Exception as e:
            print(f"Cleanup error: {e}")
            
        super().destroy()
        
    def _build_ui(self):
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill="both", expand=True)
        
        for section in SETTINGS_SECTIONS:
            sec_frame = ttk.LabelFrame(main_frame, text=section["name"], padding=10)
            sec_frame.pack(fill="x", pady=(0, 10))
            
            for field in section["fields"]:
                field_frame = ttk.Frame(sec_frame)
                field_frame.pack(fill="x", pady=5)
                
                ttk.Label(field_frame, text=field["label"]).pack(anchor="w")
                
                if field["type"] == "folder_picker":
                    picker_frame = ttk.Frame(field_frame)
                    picker_frame.pack(fill="x", pady=(2, 0))
                    
                    entry = ttk.Entry(picker_frame, textvariable=self.vars[field["key"]])
                    entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
                    ttk.Button(picker_frame, text="Browse", command=self._browse_folder, bootstyle="secondary-outline").pack(side="right")
                    
                elif field["type"] == "dropdown":
                    options_dict = {label: val for label, val in field["options"]}
                    labels = list(options_dict.keys())
                    
                    # Find current label corresponding to value
                    current_val = self.vars[field["key"]].get()
                    current_label = labels[0]
                    for lbl, val in options_dict.items():
                        if val == current_val:
                            current_label = lbl
                            break
                            
                    combo_var = tk.StringVar(value=current_label)
                    combo = ttk.Combobox(field_frame, textvariable=combo_var, values=labels, state="readonly")
                    combo.pack(fill="x", pady=(2, 0))
                    self._comboboxes.append(combo)
                    
                    def make_on_select(combo_key, opts_dict, c_var):
                        def on_select(event):
                            self.vars[combo_key].set(opts_dict[c_var.get()])
                        return on_select
                        
                    combo.bind("<<ComboboxSelected>>", make_on_select(field["key"], options_dict, combo_var))
                    
                ttk.Label(field_frame, text=field["description"], font=("", 8), foreground="gray").pack(anchor="w")
                
        # Buttons Frame
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", side="bottom")
        
        ttk.Button(btn_frame, text="Reset to Defaults", bootstyle="danger-outline", command=self.reset_to_defaults).pack(side="left")
        ttk.Button(btn_frame, text="Save & Close", bootstyle="primary", command=self.hide).pack(side="right")

    def _browse_folder(self):
        folder = filedialog.askdirectory(parent=self)
        if folder:
            self.vars["output_folder"].set(folder)
            
    def show(self):
        # Center the dialog on the parent
        self.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - self.winfo_width()) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        
        self.transient(self.parent)
        self.grab_set()
        self.parent.wait_window(self)

    def hide(self):
        # Save current UI state to the settings object
        out_folder = self.vars["output_folder"].get().strip()
        self.current_settings.output_folder = out_folder if out_folder else None
        self.current_settings.default_codec = self.vars["default_codec"].get()
        self.current_settings.theme_mode = self.vars["theme_mode"].get()
        # Cleanup first so comboboxes are destroyed and unsubscribed
        # before the theme is applied and broadcasts a style change
        self.grab_release()
        self.destroy()

        # Need to allow the Tk event loop to fully process the destroy 
        # events before we trigger the massive theme reload, otherwise 
        # ttkbootstrap style publisher will still fire on dead widgets.
        self.parent.after(50, lambda: self.on_settings_changed(self.current_settings))

    def reset_to_defaults(self):
        if messagebox.askyesno("Reset Settings", "Are you sure you want to reset all settings to their defaults?", parent=self):
            default_settings = UserSettings()
            self.current_settings = default_settings
            
            # Update variables so UI reflects defaults
            self.vars["output_folder"].set(default_settings.output_folder or "")
            self.vars["default_codec"].set(default_settings.default_codec)
            self.vars["theme_mode"].set(default_settings.theme_mode)
            
            # Since Comboboxes represent Labels, need to reconstruct their labels if we wanted them directly updated.
            # But the easiest way is to trigger hide() which will save the defaults and close.
            # The next time settings is opened, it will show defaults naturally.
            self.hide()


def create_settings_panel(parent: tk.Widget, current_settings: UserSettings, on_settings_changed: OnSettingsChanged) -> SettingsPanel:
    """Factory function to build the SettingsPanel."""
    # Ensure a fresh panel is created
    panel = SettingsPanel(parent, current_settings, on_settings_changed)
    return panel
