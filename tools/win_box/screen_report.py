"""What Windows, pyglet and the engine see on this desktop.  Run inside the interactive (RDP) session;
writes C:\\win4k\\screen_report.json.  The Windows numbers are read before pyglet declares the process DPI aware."""
import ctypes, json, os, sys

user32, shcore = ctypes.windll.user32, ctypes.windll.shcore
report = {"session": os.environ.get("SESSIONNAME"),
          "windows_unaware": {"SM_CXSCREEN": user32.GetSystemMetrics(0), "SM_CYSCREEN": user32.GetSystemMetrics(1)}}
import pyglet                                       # importing pyglet.window sets per-monitor awareness
display = pyglet.display.get_display()
screen = display.get_default_screen()
report["windows_aware"] = {"SM_CXSCREEN": user32.GetSystemMetrics(0), "SM_CYSCREEN": user32.GetSystemMetrics(1),
                           "GetDpiForSystem": user32.GetDpiForSystem()}
report["pyglet"] = {"version": pyglet.version, "dpi_scaling": pyglet.options.get("dpi_scaling"),
                    "screens": [{"width": s.width, "height": s.height, "x": s.x, "y": s.y,
                                 "scale": getattr(s, "get_scale", lambda: None)(), "dpi": getattr(s, "get_dpi", lambda: None)()}
                                for s in display.get_screens()]}
window = pyglet.window.Window(width=1280, height=800, visible=True, caption="probe 1280x800")
window.dispatch_events()
report["window_1280x800"] = {"size": window.get_size(), "framebuffer": window.get_framebuffer_size(),
                             "scale": getattr(window, "scale", None), "dpi": getattr(window, "dpi", None),
                             "location": window.get_location()}
window.close()
try:
    from saga2d import Game, Scene
    game = Game("engine probe", resolution=None, backend="pyglet", visible=True)
    game.tick(1 / 60)
    report["engine"] = {"resolution": game.resolution, "window_size": game.window_size,
                        "scale_factor": game.backend.scale_factor, "screen_size": game.backend.screen_size(),
                        "framebuffer": game.backend.window.get_framebuffer_size(), "pyglet_window_scale": game.backend.window.scale}
    game.close()
except Exception as exc:                            # the probe reports what it could; the game itself runs next
    report["engine"] = {"error": f"{type(exc).__name__}: {exc}"}
os.makedirs(r"C:\win4k", exist_ok=True)
with open(r"C:\win4k\screen_report.json", "w") as out:
    json.dump(report, out, indent=2)
print(json.dumps(report))
