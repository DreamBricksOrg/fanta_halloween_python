"""Tk interface for a portrait VLC playlist."""

import tkinter as tk
from tkinter import messagebox

from .config import ConfigError, load_config
from .playback import PlaylistPlayer
from .serial_signal import SerialNotifier
from .vlc_backend import VLCBackend


def portrait_viewport_size(screen_width, screen_height):
    """Largest centered 9:16 viewport that fits inside a screen."""
    width = min(screen_width, screen_height * 9 // 16)
    height = min(screen_height, screen_width * 16 // 9)
    return width, height


def main():
    try:
        config = load_config()
        notifier = SerialNotifier.open(config.serial_port, config.serial_baud)
    except (ConfigError, OSError, RuntimeError) as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Portrait Player", str(exc))
        root.destroy()
        raise SystemExit(1)

    root = tk.Tk()
    root.title("Portrait Playlist Player")
    root.attributes("-fullscreen", True)
    root.configure(bg="black")
    root.update_idletasks()
    width, height = portrait_viewport_size(root.winfo_screenwidth(), root.winfo_screenheight())
    video = tk.Frame(root, bg="black", width=width, height=height)
    video.place(relx=0.5, rely=0.5, anchor="center")
    video.pack_propagate(False)
    try:
        backend = VLCBackend(video)
    except RuntimeError as exc:
        messagebox.showerror("Portrait Player", str(exc), parent=root)
        root.destroy()
        notifier.close()
        raise SystemExit(1)
    player = PlaylistPlayer(config.videos, backend, notifier)

    footer = tk.Frame(video, bg="#111111")
    tk.Label(
        footer,
        text="D: hide debug  |  ← Previous  |  → Next  |  Space Pause/Resume  |  Esc Exit",
        fg="white",
        bg="#111111",
        anchor="center",
    ).pack(fill="x", padx=8, pady=8)
    controls = tk.Frame(footer, bg="#111111")
    for label, action in (("Previous", player.previous), ("Pause / Resume", player.pause_resume), ("Next", player.next)):
        tk.Button(controls, text=label, command=action).pack(side="left", expand=True, fill="x")
    controls.pack(fill="x", padx=8, pady=(0, 8))

    def toggle_debug(event=None):
        if footer.winfo_manager():
            footer.place_forget()
        else:
            footer.place(relx=0, rely=1, relwidth=1, anchor="sw")
        return "break"

    root.bind("<d>", toggle_debug)
    root.bind("<D>", toggle_debug)
    root.bind("<Left>", lambda event: player.previous())
    root.bind("<Right>", lambda event: player.next())
    root.bind("<space>", lambda event: player.pause_resume())
    root.after(150, player.start)

    def shutdown():
        player.close()
        root.destroy()

    root.bind("<Escape>", lambda event: shutdown())
    root.protocol("WM_DELETE_WINDOW", shutdown)
    root.mainloop()
