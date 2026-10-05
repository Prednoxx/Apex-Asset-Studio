"""Startup branding using the original user-supplied artwork and native UI shapes."""
import time
import tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk


class StartupSplash(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.started = time.monotonic(); self._closed = False
        self.overrideredirect(True)
        width, height = 860, 500
        self.geometry(f'{width}x{height}+{max(0,(self.winfo_screenwidth()-width)//2)}+{max(0,(self.winfo_screenheight()-height)//2)}')
        self.configure(background='white')
        canvas = tk.Canvas(self, width=width, height=height, background='white', highlightthickness=0)
        canvas.pack(fill='both', expand=True); self.canvas = canvas
        # Graphic accents are ordinary UI drawing; the supplied WebP is untouched.
        canvas.create_polygon(0, 0, 220, 0, 188, 10, 0, 10, fill='#d83b2e', outline='')
        canvas.create_polygon(790, 0, 860, 0, 860, 155, fill='#efefef', outline='')
        canvas.create_polygon(805, 0, 829, 0, 860, 69, 860, 119, fill='#d83b2e', outline='')
        canvas.create_polygon(0, 455, 355, 455, 332, 500, 0, 500, fill='#20232a', outline='')
        canvas.create_polygon(328, 500, 352, 451, 363, 451, 339, 500, fill='#d83b2e', outline='')
        try:
            with Image.open(Path(__file__).resolve().parents[1]/'resources/asuka.webp') as image:
                image = image.convert('RGBA'); image.thumbnail((350, 440))
                self.art = ImageTk.PhotoImage(image)
            canvas.create_image(190, 231, image=self.art)
        except OSError:
            canvas.create_text(190, 235, text='APEX ASSET STUDIO', fill='#20232a', font=('Segoe UI Semibold', 16))
        canvas.create_line(395, 85, 395, 345, fill='#e9e9e9', width=2)
        canvas.create_text(429, 116, text='APEX ASSET', anchor='nw', fill='#25272d', font=('Segoe UI Semibold', 31))
        canvas.create_text(429, 163, text='STUDIO', anchor='nw', fill='#d83b2e', font=('Segoe UI Semibold', 44))
        canvas.create_line(433, 290, 757, 290, fill='#e1e2e5', width=2)
        self.status = canvas.create_text(433, 313, text='Starting…', anchor='nw', fill='#535761', font=('Segoe UI', 10), width=335)
        self.lift(); self.update()

    def stage(self, message):
        if self._closed: return
        self.canvas.itemconfigure(self.status, text=message); self.update()

    def finish(self, app):
        self.stage('Ready')
        # Keep quick startups readable without claiming background work is running.
        delay = max(0, int((1.4-(time.monotonic()-self.started))*1000))
        def reveal():
            if self._closed: return
            self._closed = True; self.destroy(); app.deiconify(); app.lift()
        app.after(delay, reveal)
