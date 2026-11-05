#!/usr/bin/env python3
"""Widescreen television on the desktop.

The picture is 16:9, edge to edge, with no bezel. The window around it is
clear. Click the picture for the next channel. Static plays until that
channel locks. Drag the picture to move it, including over the top bar and
the dock. Drag an edge, or scroll the picture, to resize. The line under
the picture is the volume.

Sits above the desktop icons and behind ordinary windows. Opens through
XWayland so it can remember its place.
"""
from __future__ import annotations

import ast
import json
import os
import signal
import subprocess
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)

sys.path[:0] = [
    str(Path(__file__).resolve().parent),
    str(Path.home() / ".local" / "lib"),
]
from desklet_geometry import prefer_xwayland  # noqa: E402

prefer_xwayland()

import cairo  # noqa: E402
import gi  # noqa: E402

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gdk, GLib, Gst, Gtk  # noqa: E402

from desklet_geometry import (  # noqa: E402
    DeskletChrome,
    DeskletPlacement,
    _gestures,
    apply_rect,
    edge_name_at,
    prepare_desktop_window,
)

GLib.set_prgname("lee-tv")

HOME = Path.home()
PRGNAME = "lee-tv"
APP_ID = "uk.lee.tv"
CONFIG_DIR = HOME / ".config" / "lee-tv"
CONFIG = CONFIG_DIR / "config.json"
PID = HOME / ".cache" / "lee-tv.pid"
LOG = Path("/tmp/tv-widget.log")
ICON = HOME / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "lee-tv.png"
APP_DESKTOP = HOME / ".local" / "share" / "applications" / "lee-tv.desktop"
AUTOSTART = HOME / ".config" / "autostart" / "lee-tv.desktop"

# 1080p widescreen. The picture stays 16:9 at every size.
TARGET_W = 1920
TARGET_H = 1080
BAR = 36
MIN_W = 480
MIN_PH = 270
GRIP = 14
CLICK_SLOP = 6
STATIC_MS = 700
GIVE_UP_MS = 12000
FRAME_ANCHOR = 16
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Freeview lineup where the broadcaster publishes an open HLS stream.
# Checked from this network on 2 Nov 2026. ITV, Channel 4, Channel 5,
# UKTV and Sky's main channels are locked, so they are not listed.
# BBC One is the London feed.


def bbc_uk(service: str) -> str:
    return (
        "https://vs-hls-pushb-uk-live.akamaized.net/x=4/i="
        f"urn:bbc:pips:service:{service}/pc_hd_abr_v2.m3u8"
    )


def bbc_legacy(service: str) -> str:
    return (
        "https://vs-hls-push-uk-live.akamaized.net/x=4/i="
        f"urn:bbc:pips:service:{service}/iptv_hd_abr_v1.m3u8"
    )


def bbc_world(service: str) -> str:
    return (
        "https://vs-hls-pushb-ww-live.akamaized.net/x=4/i="
        f"urn:bbc:pips:service:{service}/pc_hd_abr_v2.m3u8"
    )


GROUP_ORDER = ("BBC", "Regions", "Kids", "Entertainment", "Shopping", "News")

CHANNELS = [
    {"group": "BBC", "name": "BBC One", "url": bbc_legacy("bbc_one_london")},
    {"group": "BBC", "name": "BBC Two", "url": bbc_legacy("bbc_two_hd")},
    {"group": "BBC", "name": "BBC Three", "url": bbc_uk("bbc_three_hd")},
    {"group": "BBC", "name": "BBC Four", "url": bbc_uk("bbc_four_hd")},
    {"group": "BBC", "name": "BBC Scotland", "url": bbc_uk("bbc_scotland_hd")},
    {"group": "BBC", "name": "BBC Alba", "url": bbc_uk("bbc_alba")},
    {"group": "BBC", "name": "BBC News", "url": bbc_legacy("bbc_news_channel_hd")},
    {"group": "BBC", "name": "BBC Parliament", "url": bbc_uk("bbc_parliament")},
    {"group": "BBC", "name": "BBC Red Button", "url": bbc_uk("red_button_one")},
    {"group": "BBC", "name": "BBC Arabic", "url": bbc_world("bbc_arabic_tv")},
    {"group": "BBC", "name": "BBC Persian", "url": bbc_world("bbc_persian_tv")},
    {"group": "BBC", "name": "BBC Pashto", "url": bbc_world("bbc_afghan_tv")},
    {"group": "Regions", "name": "BBC One Channel Islands", "url": bbc_uk("bbc_one_channel_islands")},
    {"group": "Regions", "name": "BBC One East", "url": bbc_uk("bbc_one_east")},
    {"group": "Regions", "name": "BBC One East Midlands", "url": bbc_uk("bbc_one_east_midlands")},
    {"group": "Regions", "name": "BBC One East Yorkshire", "url": bbc_uk("bbc_one_east_yorkshire")},
    {"group": "Regions", "name": "BBC One North East", "url": bbc_uk("bbc_one_north_east")},
    {"group": "Regions", "name": "BBC One North West", "url": bbc_uk("bbc_one_north_west")},
    {"group": "Regions", "name": "BBC One Northern Ireland", "url": bbc_uk("bbc_one_northern_ireland_hd")},
    {"group": "Regions", "name": "BBC One Scotland", "url": bbc_uk("bbc_one_scotland_hd")},
    {"group": "Regions", "name": "BBC One South", "url": bbc_uk("bbc_one_south")},
    {"group": "Regions", "name": "BBC One South East", "url": bbc_uk("bbc_one_south_east")},
    {"group": "Regions", "name": "BBC One South West", "url": bbc_uk("bbc_one_south_west")},
    {"group": "Regions", "name": "BBC One Wales", "url": bbc_uk("bbc_one_wales_hd")},
    {"group": "Regions", "name": "BBC One West", "url": bbc_uk("bbc_one_west")},
    {"group": "Regions", "name": "BBC One West Midlands", "url": bbc_uk("bbc_one_west_midlands")},
    {"group": "Regions", "name": "BBC One Yorkshire", "url": bbc_uk("bbc_one_yorks")},
    {"group": "Regions", "name": "BBC Two Northern Ireland", "url": bbc_uk("bbc_two_northern_ireland_hd")},
    {"group": "Kids", "name": "CBBC", "url": bbc_uk("cbbc_hd")},
    {"group": "Kids", "name": "CBeebies", "url": bbc_uk("cbeebies_hd")},
    {"group": "Kids", "name": "Pop", "url": "https://amg01753-narrativeentert-popkids-lggb-xyy5k.amagi.tv/ts-eu-w1-n2/playlist/amg01753-narrativeentert-popkids-lggb/playlist.m3u8"},
    {"group": "Kids", "name": "Tiny Pop", "url": "https://amg01753-narrativeuk-amg01753c1-lg-gb-1830.playouts.now.amagi.tv/playlist/amg01753-narrativeuk-tinypop-lggb/playlist.m3u8"},
    {"group": "Kids", "name": "Pop Up", "url": "https://amg01753-amg01753c9-samsung-gb-8005.playouts.now.amagi.tv/ts-eu-w1-n2/playlist/amg01753-narrativeuk-popup-samsunggb/playlist.m3u8"},
    {"group": "Entertainment", "name": "Blaze", "url": "https://live-blaze-ssai.simplestreamcdn.com/v1/master/774d979dd66704abea7c5b62cb34c6815fda0d35/blaze-live-broadcast-scte/index.m3u8"},
    {"group": "Entertainment", "name": "GREAT! movies", "url": "https://amg01753-narrativeuk-amg01753c3-lg-gb-1833.playouts.now.amagi.tv/playlist/amg01753-narrativeuk-greatmovies-lggb/playlist.m3u8"},
    {"group": "Entertainment", "name": "GREAT! romance", "url": "https://amg01753-narrativeuk-amg01753c2-lg-gb-1832.playouts.now.amagi.tv/playlist/amg01753-narrativeuk-greatchristmas-lggb/playlist.m3u8"},
    {"group": "Entertainment", "name": "True Crime", "url": "https://b6cca454.wurl.com/master/f36d25e7e52f1ba8d7e56eb859c636563214f541/U2Ftc3VuZy1nYl9UcnVlQ3JpbWVVS2Zyb21DQlNSZWFsaXR5X0hMUw/playlist.m3u8"},
    {"group": "Entertainment", "name": "Trace UK", "url": "https://channels.trace.plus/Traceprod/UK_FAST_hd/index.m3u8"},
    {"group": "Entertainment", "name": "Red Bull TV", "url": "https://rbmn-live.akamaized.net/hls/live/590964/BoRB-AT/master.m3u8"},
    {"group": "Entertainment", "name": "talkSPORT", "url": "https://af7a8b4e.wurl.com/master/f36d25e7e52f1ba8d7e56eb859c636563214f541/TEctZ2JfdGFsa1NQT1JUX0hMUw/playlist.m3u8"},
    {"group": "Shopping", "name": "QVC", "url": "https://qvcuk-live.akamaized.net/hls/live/2097112/qvc/master.m3u8"},
    {"group": "Shopping", "name": "QVC Beauty", "url": "https://qvcuk-live.akamaized.net/hls/live/2097112/qby/master.m3u8"},
    {"group": "Shopping", "name": "Gemporia", "url": "https://lo3.gemporia.com/abrgemporiaukgfx/smil:livestream.smil/playlist.m3u8"},
    {"group": "Shopping", "name": "Hobby Maker", "url": "https://lo3.gemporia.com/abrhobbymakerukgfx/smil:livestreamFullHD.smil/playlist.m3u8"},
    {"group": "Shopping", "name": "TJC", "url": "https://cdn-shop-lc-01.akamaized.net/Content/HLS_HLS/Live/channel(TJCOTT)/index.m3u8"},
    {"group": "News", "name": "GB News", "url": "https://live-gbnews.simplestreamcdn.com/live5/gbnews/bitrate1.isml/manifest.m3u8"},
    {"group": "News", "name": "TalkTV", "url": "https://488f4ce4.wurl.com/master/f36d25e7e52f1ba8d7e56eb859c636563214f541/TEctZ2JfVGFsa19ITFM/playlist.m3u8"},
    {"group": "News", "name": "Sky News Weather", "url": "https://distro001-gb-hls1-prd.delivery.skycdp.com/easel_cdn/ngrp:weather_loop.stream_all/playlist.m3u8"},
    {"group": "News", "name": "CNBC", "url": "https://amg01079-nbcuuk-amg01079c2-samsung-gb-1258.playouts.now.amagi.tv/playlist.m3u8"},
    {"group": "News", "name": "DW English", "url": "https://dwamdstream102.akamaized.net/hls/live/2015525/dwstream102/master.m3u8"},
    {"group": "News", "name": "DW Español", "url": "https://dwamdstream104.akamaized.net/hls/live/2015530/dwstream104/master.m3u8"},
    {"group": "News", "name": "DW Arabic", "url": "https://dwamdstream103.akamaized.net/hls/live/2015526/dwstream103/master.m3u8"},
    {"group": "News", "name": "France 24", "url": "https://amg00106-france24-france24-samsunguk-qvpp8.amagi.tv/playlist/amg00106-france24-france24-samsunguk/playlist.m3u8"},
    {"group": "News", "name": "Bloomberg", "url": "https://www.bloomberg.com/media-manifest/streams/us.m3u8"},
    {"group": "News", "name": "Al Jazeera Arabic", "url": "https://live-hls-web-aja.getaj.net/AJA/index.m3u8"},
    {"group": "News", "name": "CGTN", "url": "https://english-livebkali.cgtn.com/live/encgtn.m3u8"},
    {"group": "News", "name": "VOA Africa", "url": "https://voa-ingest.akamaized.net/hls/live/2033874/tvmc06/playlist.m3u8"},
    {"group": "News", "name": "TRT World", "url": "https://tv-trtworld.medya.trt.com.tr/master.m3u8"},
]

CLEAR_STATES = (
    Gtk.StateFlags.NORMAL,
    Gtk.StateFlags.ACTIVE,
    Gtk.StateFlags.PRELIGHT,
    Gtk.StateFlags.SELECTED,
    Gtk.StateFlags.INSENSITIVE,
    Gtk.StateFlags.FOCUSED,
    Gtk.StateFlags.BACKDROP,
)
TRANS = Gdk.RGBA(0, 0, 0, 0)


def log(message: str) -> None:
    line = time.strftime("%H:%M:%S ") + message
    try:
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
    except OSError:
        pass


def fit_aspect(
    x: int,
    y: int,
    w: int,
    h: int,
    nick: str,
    ox: int,
    oy: int,
    ow: int,
    oh: int,
    bar: int = BAR,
    min_w: int = MIN_W,
) -> tuple[int, int, int, int]:
    """Lock the picture to 16:9. The bar under it stays a fixed height."""
    vertical = nick in ("north", "south")
    if vertical:
        ph = max(MIN_PH, int(h) - bar)
        w = max(min_w, int(round(ph * 16 / 9)))
        h = ph + bar
    else:
        w = max(min_w, int(w))
        ph = max(MIN_PH, int(round(w * 9 / 16)))
        w = max(min_w, int(round(ph * 16 / 9)))
        h = ph + bar
    if "west" in nick:
        x = int(ox) + int(ow) - int(w)
    if "north" in nick:
        y = int(oy) + int(oh) - int(h)
    return int(x), int(y), int(w), int(h)


def default_window(work_w: int, work_h: int) -> tuple[int, int]:
    """1080p where it fits, otherwise the largest 16:9 that fits."""
    avail_w = max(MIN_W, int(work_w) - 32)
    avail_h = max(MIN_PH + BAR, int(work_h) - 32)
    pw = min(TARGET_W, avail_w)
    ph = int(round(pw * 9 / 16))
    if ph + BAR > avail_h:
        ph = max(MIN_PH, avail_h - BAR)
        pw = max(MIN_W, int(round(ph * 16 / 9)))
        ph = int(round(pw * 9 / 16))
    return int(pw), int(ph + BAR)


def free_insets(width: int, height: int, strut_left: int = 0, strut_top: int = 0) -> tuple[int, int, int, int]:
    """Shadow so the screen can cover the dock and the top bar.

    A 16px frame on a 1080-wide window makes Mutter grow the window to the
    monitor, so the frame stays a real slice of the screen.
    """
    width = max(int(width), 2)
    height = max(int(height), 2)
    left = min(max(0, int(strut_left)) + 48, max(1, width // 5))
    right = min(48, max(1, width // 5))
    top = min(max(0, int(strut_top)) + 48, max(1, height // 5))
    bottom = min(48, max(1, height // 5))
    if left + right > width - FRAME_ANCHOR:
        left = min(left, max(1, width - FRAME_ANCHOR - 1))
        right = max(0, width - FRAME_ANCHOR - left)
    if top + bottom > height - FRAME_ANCHOR:
        top = min(top, max(1, height - FRAME_ANCHOR - 1))
        bottom = max(0, height - FRAME_ANCHOR - top)
    return int(left), int(right), int(top), int(bottom)


def monitor_work() -> tuple[int, int, int, int]:
    display = Gdk.Display.get_default()
    if display is None or display.get_n_monitors() < 1:
        return 0, 0, 1920, 1080
    monitor = display.get_primary_monitor() or display.get_monitor(0)
    if monitor is None:
        return 0, 0, 1920, 1080
    work = monitor.get_workarea()
    return int(work.x), int(work.y), int(work.width), int(work.height)


def load_cfg() -> dict:
    cfg = {
        "x": None,
        "y": None,
        "w": TARGET_W,
        "h": TARGET_H + BAR,
        "volume": 0.7,
        "channel": -1,
    }
    try:
        saved = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        saved = {}
    if isinstance(saved, dict):
        cfg.update({key: saved.get(key, cfg[key]) for key in cfg})
    try:
        cfg["volume"] = min(1.0, max(0.0, float(cfg["volume"])))
    except (TypeError, ValueError):
        cfg["volume"] = 0.7
    try:
        cfg["channel"] = int(cfg["channel"])
    except (TypeError, ValueError):
        cfg["channel"] = -1
    if cfg["channel"] < -1 or cfg["channel"] >= len(CHANNELS):
        cfg["channel"] = -1
    return cfg


def write_state(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    blob = {
        "x": cfg.get("x"),
        "y": cfg.get("y"),
        "w": int(cfg.get("w") or TARGET_W),
        "h": int(cfg.get("h") or TARGET_H + BAR),
        "volume": float(cfg.get("volume") or 0),
        "channel": int(cfg.get("channel") if cfg.get("channel") is not None else -1),
    }
    CONFIG.write_text(json.dumps(blob, indent=2) + "\n", encoding="utf-8")


def command_path() -> str:
    """Launcher path written into the desktop file. ~/bin/tv on this machine."""
    for candidate in (Path.home() / "bin" / "tv", Path.home() / ".local" / "bin" / "tv"):
        if candidate.exists():
            return str(candidate)
    return str(Path(__file__).resolve())


def desktop_file() -> str:
    return "\n".join(
        (
            "[Desktop Entry]",
            "Version=1.0",
            "Type=Application",
            "Name=TV",
            "Comment=Widescreen television. Click the picture for the next channel.",
            f"Exec={command_path()}",
            f"Icon={ICON}",
            "Terminal=false",
            "Categories=AudioVideo;Video;TV;",
            "StartupNotify=false",
            "StartupWMClass=lee-tv",
            "Keywords=tv;television;channels;screen;widescreen;",
            "",
        )
    )


def install_launchers() -> None:
    write_icon()
    body = desktop_file()
    for path in (APP_DESKTOP,):
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text(encoding="utf-8") != body:
            path.write_text(body, encoding="utf-8")
    if not AUTOSTART.exists():
        AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
        AUTOSTART.write_text(
            body + "Hidden=true\nX-GNOME-Autostart-enabled=false\n",
            encoding="utf-8",
        )


def autostart_enabled() -> bool:
    if not AUTOSTART.exists():
        return False
    hidden = False
    enabled = True
    for line in AUTOSTART.read_text(encoding="utf-8").splitlines():
        if line.startswith("Hidden="):
            hidden = line.split("=", 1)[1].strip().lower() == "true"
        elif line.startswith("X-GNOME-Autostart-enabled="):
            enabled = line.split("=", 1)[1].strip().lower() == "true"
    return enabled and not hidden


def set_autostart(enabled: bool) -> None:
    install_launchers()
    lines = AUTOSTART.read_text(encoding="utf-8").splitlines()
    found_enabled = False
    found_hidden = False
    rewritten = []
    for line in lines:
        if line.startswith("X-GNOME-Autostart-enabled="):
            rewritten.append("X-GNOME-Autostart-enabled=" + ("true" if enabled else "false"))
            found_enabled = True
        elif line.startswith("Hidden="):
            rewritten.append("Hidden=" + ("false" if enabled else "true"))
            found_hidden = True
        else:
            rewritten.append(line)
    if not found_enabled:
        rewritten.append("X-GNOME-Autostart-enabled=" + ("true" if enabled else "false"))
    if not found_hidden:
        rewritten.append("Hidden=" + ("false" if enabled else "true"))
    AUTOSTART.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def paint_clear(widget: Gtk.Widget) -> None:
    context = widget.get_style_context()
    context.remove_class("background")
    for state in CLEAR_STATES:
        try:
            widget.override_background_color(state, TRANS)
        except Exception:
            pass


def write_icon() -> None:
    ICON.parent.mkdir(parents=True, exist_ok=True)
    side = 256
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, side, side)
    cr = cairo.Context(surface)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_rgba(0, 0, 0, 0)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)
    cr.new_sub_path()
    cr.arc(side - 28, 28, 36, -1.5708, 0)
    cr.arc(side - 28, side - 28, 36, 0, 1.5708)
    cr.arc(28, side - 28, 36, 1.5708, 3.1416)
    cr.arc(28, 28, 36, 3.1416, 4.7124)
    cr.close_path()
    cr.set_source_rgba(0.043, 0.239, 0.239, 1)
    cr.fill()
    cr.rectangle(48, 58, 160, 90)
    cr.set_source_rgba(1, 1, 1, 0.92)
    cr.fill()
    cr.rectangle(78, 168, 100, 8)
    cr.set_source_rgba(1, 1, 1, 0.7)
    cr.fill()
    cr.arc(128, 172, 9, 0, 6.3)
    cr.set_source_rgba(1, 1, 1, 1)
    cr.fill()
    surface.write_to_png(str(ICON))


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        text = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
    except OSError:
        return False
    return "lee_tv_widget.py" in text or PRGNAME in text


def session_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    bus = Path(env["XDG_RUNTIME_DIR"]) / "bus"
    if bus.exists():
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={bus}")
    env.setdefault("DISPLAY", ":0")
    return env


def pin_panel() -> None:
    """Pin the launcher on the left dock, next to Old Television."""
    desktop_id = APP_DESKTOP.name
    try:
        raw = subprocess.check_output(
            ["gsettings", "get", "org.gnome.shell", "favorite-apps"],
            env=session_env(),
            text=True,
        )
        apps = ast.literal_eval(raw.strip())
    except (OSError, subprocess.CalledProcessError, SyntaxError, ValueError) as exc:
        log(f"pin failed {exc}")
        return
    if not isinstance(apps, list) or desktop_id in apps:
        return
    if "lee-old-television.desktop" in apps:
        apps.insert(apps.index("lee-old-television.desktop") + 1, desktop_id)
    else:
        apps.insert(0, desktop_id)
    payload = "[" + ", ".join(f"'{item}'" for item in apps) + "]"
    try:
        subprocess.check_call(
            ["gsettings", "set", "org.gnome.shell", "favorite-apps", payload],
            env=session_env(),
        )
        log("pinned to panel")
    except (OSError, subprocess.CalledProcessError) as exc:
        log(f"pin set failed {exc}")


def claim_pid(replace: bool) -> None:
    PID.parent.mkdir(parents=True, exist_ok=True)
    if PID.exists():
        text = PID.read_text(encoding="utf-8").strip()
        if text.isdigit():
            old = int(text)
            if old != os.getpid() and pid_alive(old):
                if not replace:
                    log(f"already running as {old}")
                    print("TV is already on the desktop.", file=sys.stderr)
                    raise SystemExit(0)
                os.kill(old, signal.SIGTERM)
                for _ in range(30):
                    if not pid_alive(old):
                        break
                    time.sleep(0.05)
    PID.write_text(str(os.getpid()) + "\n", encoding="utf-8")


def release_pid() -> None:
    try:
        if PID.exists() and PID.read_text(encoding="utf-8").strip() == str(os.getpid()):
            PID.unlink()
    except OSError:
        pass


def edge_nick(edge) -> str:
    if edge is None:
        return ""
    name = getattr(edge, "value_nick", "") or ""
    return str(name).replace("_", "-")


class TVWindow(Gtk.Window):
    def __init__(self, cfg: dict):
        super().__init__(title="TV")
        prepare_desktop_window(self)
        self.cfg = cfg
        self.volume = float(cfg["volume"])
        self.channel = int(cfg["channel"])
        self.token = 0
        self._status = ""
        self._hissing = False
        self._noise = None
        self._snow_until = 0.0
        self._scroll_at = 0.0
        self._shadow_for = None
        self._save_id = None
        self._resize = None
        self._vol_drag = False
        self._alive = True
        self._menu = None
        self._frame = None
        self._frame_pending = False
        self._frame_at = 0.0
        self.set_name("tv")
        self.set_role("tv")
        self.set_app_paintable(True)
        try:
            self.set_icon_from_file(str(ICON))
        except Exception:
            pass

        screen = self.get_screen()
        visual = screen.get_rgba_visual() if screen is not None else None
        if visual is not None:
            self.set_visual(visual)
        css = Gtk.CssProvider()
        css.load_from_data(b"window, box, overlay { background-color: transparent; }")
        Gtk.StyleContext.add_provider_for_screen(
            screen, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.connect("draw", self._on_window_draw)
        self.connect("realize", self._on_realize)
        self.connect("map-event", self._on_map)
        self.connect("configure-event", self._on_configure)
        self.connect("key-press-event", self._on_key)
        self.connect("window-state-event", self._on_window_state)
        self.connect("destroy", self._on_destroy)

        self.glass = Gtk.DrawingArea()
        self.glass.set_app_paintable(True)
        self.glass.set_hexpand(True)
        self.glass.set_vexpand(True)
        self.glass.connect("draw", self._draw_glass)
        self.snow = Gtk.DrawingArea()
        self.snow.set_app_paintable(True)
        self.snow.connect("draw", self._draw_snow)

        self.picture = Gtk.Overlay()
        self.picture.set_app_paintable(True)
        self.picture.add(self.glass)
        self.picture.add_overlay(self.snow)
        self.picture.connect("get-child-position", self._place_snow)
        self.picture.set_hexpand(True)
        self.picture.set_vexpand(True)

        self.slider = Gtk.DrawingArea()
        self.slider.set_app_paintable(True)
        self.slider.set_size_request(-1, BAR)
        self.slider.connect("draw", self._draw_slider)
        self.slider.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.BUTTON1_MOTION_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.slider.connect("button-press-event", self._slider_press)
        self.slider.connect("motion-notify-event", self._slider_motion)
        self.slider.connect("button-release-event", self._slider_release)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.pack_start(self.picture, True, True, 0)
        box.pack_start(self.slider, False, False, 0)
        self.add(box)

        self._place_default()
        self.placement = DeskletPlacement(
            self,
            self._load_geo,
            self._save_geo,
            min_w=MIN_W,
            min_h=MIN_PH + BAR,
            on_quit=self._quit,
        )
        self.placement.apply_before_show()
        self.chrome = DeskletChrome(
            self,
            min_w=MIN_W,
            min_h=MIN_PH + BAR,
            grip=GRIP,
            click_slop=CLICK_SLOP,
            on_click=self._on_picture_click,
            constrain=self._constrain,
            on_done=self._on_gesture_done,
            placement=self.placement,
        )
        for widget in (self.glass, self.snow, self.picture):
            self.chrome.watch(widget)
            widget.connect("button-press-event", self._on_button)
            widget.connect("scroll-event", self._on_scroll)
            widget.add_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)
            self.placement.watch(widget)

        self.vbin = Gst.parse_bin_from_description(
            "videoconvert ! videoscale ! video/x-raw,format=BGRA ! "
            "appsink name=frames emit-signals=true max-buffers=1 drop=true sync=true",
            True,
        )
        self.frames = self.vbin.get_by_name("frames")
        self.frames.connect("new-sample", self._on_sample)
        self.player = Gst.ElementFactory.make("playbin", "tv")
        self.player.set_property("video-sink", self.vbin)
        self.player.set_property("volume", self.volume)
        # Video, audio, and the soft volume flag. No visualiser window.
        self.player.set_property("flags", 1 | 2 | 16)
        self.player.connect("source-setup", self._on_source)
        bus = self.player.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus)

        self.hiss = None
        self.hiss_vol = None
        try:
            self.hiss = Gst.parse_launch(
                "audiotestsrc wave=white-noise is-live=true ! "
                "volume name=v volume=0.0 ! audioconvert ! audioresample ! autoaudiosink"
            )
            self.hiss_vol = self.hiss.get_by_name("v")
        except Exception as exc:
            log(f"hiss unavailable: {exc}")

        GLib.timeout_add(50, self._tick_snow)
        if self.channel >= 0:
            GLib.idle_add(self._tune, self.channel)
        else:
            self._show_snow("")
            self._hiss(True)

    def _place_default(self) -> None:
        wx, wy, ww, wh = monitor_work()
        if not isinstance(self.cfg.get("w"), int) or self.cfg["w"] < MIN_W:
            self.cfg["w"], self.cfg["h"] = default_window(ww, wh)
        else:
            _x, _y, w, h = fit_aspect(0, 0, int(self.cfg["w"]), int(self.cfg["h"]), "east", 0, 0, 0, 0)
            self.cfg["w"], self.cfg["h"] = w, h
        if self.cfg.get("x") is None or self.cfg.get("y") is None:
            self.cfg["x"] = int(wx + max(0, (ww - self.cfg["w"]) / 2))
            self.cfg["y"] = int(wy + max(0, (wh - self.cfg["h"]) / 2))
        self.set_default_size(int(self.cfg["w"]), int(self.cfg["h"]))

    def _load_geo(self):
        return self.cfg.get("x"), self.cfg.get("y"), int(self.cfg["w"]), int(self.cfg["h"])

    def _save_geo(self, x: int, y: int, w: int, h: int) -> None:
        snapped = fit_aspect(int(x), int(y), int(w), int(h), "east", int(x), int(y), int(w), int(h))
        # A move keeps the corner the pointer left. Only a resize snaps the aspect.
        self.cfg["x"] = int(x)
        self.cfg["y"] = int(y)
        if abs(int(w) - snapped[2]) > 8 or abs(int(h) - snapped[3]) > 8:
            self.cfg["w"], self.cfg["h"] = snapped[2], snapped[3]
        else:
            self.cfg["w"], self.cfg["h"] = int(w), int(h)
        self._write()

    def _persist(self) -> None:
        if self._save_id is not None:
            GLib.source_remove(self._save_id)
        self._save_id = GLib.timeout_add(300, self._write)

    def _write(self) -> bool:
        self._save_id = None
        try:
            if self.get_mapped():
                x, y = self.get_position()
                self.cfg["x"], self.cfg["y"] = int(x), int(y)
            write_state(self.cfg)
        except OSError as exc:
            log(f"save failed: {exc}")
        return False

    def _panel_struts(self) -> tuple[int, int]:
        try:
            display = self.get_display() or Gdk.Display.get_default()
            if display is None or display.get_n_monitors() < 1:
                return 0, 0
            monitor = None
            gdk_window = self.get_window()
            if gdk_window is not None:
                monitor = display.get_monitor_at_window(gdk_window)
            if monitor is None:
                monitor = display.get_primary_monitor() or display.get_monitor(0)
            if monitor is None:
                return 0, 0
            geo = monitor.get_geometry()
            work = monitor.get_workarea()
            return max(0, int(work.x - geo.x)), max(0, int(work.y - geo.y))
        except Exception:
            return 0, 0

    def _sync_free_shadow(self) -> None:
        gdk_window = self.get_window()
        if gdk_window is None:
            return
        width, height = int(self.cfg["w"]), int(self.cfg["h"])
        if width < 2 or height < 2 or self._shadow_for == (width, height):
            return
        insets = free_insets(width, height, *self._panel_struts())
        self._shadow_for = (width, height)
        try:
            gdk_window.set_shadow_width(*insets)
            if self.get_mapped():
                self.resize(width, height)
                GLib.idle_add(self._finish_shadow, width, height)
        except Exception as exc:
            log(f"shadow: {exc}")

    def _finish_shadow(self, width: int, height: int) -> bool:
        if (int(self.cfg["w"]), int(self.cfg["h"])) != (int(width), int(height)):
            return False
        current_w, current_h = self.get_size()
        if int(current_w) != int(width) or int(current_h) != int(height):
            self.resize(int(width), int(height))
        return False

    def _on_window_state(self, _widget, event) -> bool:
        state = int(event.new_window_state)
        if state & int(Gdk.WindowState.MAXIMIZED):
            GLib.idle_add(self._enforce_size)
        return False

    def _on_realize(self, *_args) -> bool:
        self._sync_free_shadow()
        for widget in (self, self.picture, self.snow, self.slider):
            paint_clear(widget)
        return False

    def _on_map(self, *_args) -> bool:
        try:
            Gdk.notify_startup_complete()
        except Exception:
            pass
        self._clear_opaque(self)
        self._clear_opaque(self.slider)
        self._clear_opaque(self.snow)
        self.unmaximize()
        self.set_urgency_hint(False)
        gdk_window = self.get_window()
        if gdk_window is not None:
            gdk_window.set_urgency_hint(False)
        width, height = self.get_size()
        log(
            f"open {width}x{height} at {self.cfg.get('x')},{self.cfg.get('y')} "
            f"asked {self.cfg.get('w')}x{self.cfg.get('h')}"
        )
        for delay in (60, 250, 800, 1600):
            GLib.timeout_add(delay, self._enforce_size)
        return False

    def _enforce_size(self) -> bool:
        if not self._alive or id(self) in _gestures or self._resize is not None:
            return False
        try:
            if self.is_maximized():
                self.unmaximize()
            x, y = self.get_position()
            w, h = self.get_size()
        except Exception:
            return False
        want_x, want_y = int(self.cfg["x"]), int(self.cfg["y"])
        want_w, want_h = int(self.cfg["w"]), int(self.cfg["h"])
        if abs(w - want_w) > 2 or abs(h - want_h) > 2 or abs(x - want_x) > 12 or abs(y - want_y) > 12:
            log(f"snap {x},{y} {w}x{h} -> {want_x},{want_y} {want_w}x{want_h}")
            self.unmaximize()
            self.resize(want_w, want_h)
            self.move(want_x, want_y)
        return False

    def _on_configure(self, *_args) -> bool:
        self._sync_free_shadow()
        return False

    def _clear_opaque(self, widget: Gtk.Widget) -> None:
        gdk_window = widget.get_window()
        if gdk_window is None:
            return
        try:
            gdk_window.set_opaque_region(cairo.Region())
        except Exception as exc:
            log(f"clear plate {exc}")

    def _on_window_draw(self, _widget, context: cairo.Context) -> bool:
        context.set_operator(cairo.OPERATOR_SOURCE)
        context.set_source_rgba(0, 0, 0, 0)
        context.paint()
        context.set_operator(cairo.OPERATOR_OVER)
        return False

    def _place_snow(self, overlay, widget, allocation) -> bool:
        if widget is not self.snow:
            return False
        rect = overlay.get_allocation()
        allocation.x = 0
        allocation.y = 0
        allocation.width = max(1, int(rect.width))
        allocation.height = max(1, int(rect.height))
        return True

    def _retune_noise(self) -> None:
        width, height = 160, 90
        if self._noise is None:
            self._noise = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        data = self._noise.get_data()
        raw = os.urandom(width * height)
        view = memoryview(data)
        offset = 0
        for value in raw:
            view[offset] = value
            view[offset + 1] = value
            view[offset + 2] = value
            view[offset + 3] = 255
            offset += 4
        self._noise.mark_dirty()

    def _tick_snow(self) -> bool:
        if not self._alive:
            return False
        if self.snow.get_visible():
            self._retune_noise()
            self.snow.queue_draw()
        return True

    def _on_sample(self, sink):
        sample = sink.emit("pull-sample")
        if sample is None or self._frame_pending:
            return Gst.FlowReturn.OK
        now = time.monotonic()
        if self._frame is not None and now - self._frame_at < 0.05:
            return Gst.FlowReturn.OK
        caps = sample.get_caps()
        if caps is None or caps.get_size() < 1:
            return Gst.FlowReturn.OK
        structure = caps.get_structure(0)
        ok_w, width = structure.get_int("width")
        ok_h, height = structure.get_int("height")
        if not ok_w or not ok_h:
            return Gst.FlowReturn.OK
        width, height = int(width), int(height)
        if width < 2 or height < 2 or width > 4096 or height > 2160:
            return Gst.FlowReturn.OK
        buf = sample.get_buffer()
        if buf is None:
            return Gst.FlowReturn.OK
        ok, mapped = buf.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.FlowReturn.OK
        try:
            raw = mapped.data
            if len(raw) < width * 4 * height or len(raw) % height != 0:
                return Gst.FlowReturn.OK
            stride = len(raw) // height
            if stride < width * 4:
                return Gst.FlowReturn.OK
            self._frame_at = now
            self._frame = (width, height, stride, bytes(raw))
        finally:
            buf.unmap(mapped)
        if self._frame is None:
            return Gst.FlowReturn.OK
        self._frame_pending = True
        GLib.idle_add(self._frame_ready)
        return Gst.FlowReturn.OK

    def _frame_ready(self) -> bool:
        self._frame_pending = False
        if not self._alive:
            return False
        self.glass.queue_draw()
        if self.snow.get_visible() and self._frame is not None:
            self._reveal(self.token)
        return False

    def _draw_glass(self, widget, context: cairo.Context) -> bool:
        width = max(1, int(widget.get_allocated_width()))
        height = max(1, int(widget.get_allocated_height()))
        context.set_operator(cairo.OPERATOR_SOURCE)
        context.set_source_rgba(0, 0, 0, 1)
        context.paint()
        frame = self._frame
        if frame is None:
            return True
        fw, fh, stride, raw = frame
        if fw < 2 or fh < 2 or stride < fw * 4 or len(raw) < stride * fh:
            return True
        try:
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, fw, fh)
            dest = surface.get_data()
            dst_stride = surface.get_stride()
            row_bytes = fw * 4
            for y in range(fh):
                src = y * stride
                dst = y * dst_stride
                dest[dst:dst + row_bytes] = raw[src:src + row_bytes]
            surface.mark_dirty()
            scale = min(width / fw, height / fh)
            dw = fw * scale
            dh = fh * scale
            context.set_operator(cairo.OPERATOR_OVER)
            context.save()
            context.translate((width - dw) / 2, (height - dh) / 2)
            context.scale(scale, scale)
            context.set_source_surface(surface, 0, 0)
            context.get_source().set_filter(cairo.FILTER_BILINEAR)
            context.paint()
            context.restore()
        except Exception as exc:
            log(f"picture: {exc}")
        return True

    def _draw_snow(self, widget, context: cairo.Context) -> bool:
        width = max(1, int(widget.get_allocated_width()))
        height = max(1, int(widget.get_allocated_height()))
        context.set_operator(cairo.OPERATOR_SOURCE)
        if self._noise is None:
            self._retune_noise()
        context.save()
        context.scale(width / 160.0, height / 90.0)
        context.set_source_surface(self._noise, 0, 0)
        context.get_source().set_filter(cairo.FILTER_NEAREST)
        context.paint()
        context.restore()
        if self._status:
            context.set_operator(cairo.OPERATOR_OVER)
            context.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            context.set_font_size(max(22, width * 0.042))
            _xb, _yb, tw, th, _xa, _ya = context.text_extents(self._status)
            context.move_to((width - tw) / 2, (height + th) / 2)
            context.set_source_rgba(0, 0, 0, 0.55)
            context.text_path(self._status)
            context.fill()
            context.move_to((width - tw) / 2 - 1, (height + th) / 2 - 1)
            context.set_source_rgba(1, 1, 1, 0.94)
            context.show_text(self._status)
        return True

    def _draw_slider(self, widget, context: cairo.Context) -> bool:
        width = max(1, int(widget.get_allocated_width()))
        height = max(1, int(widget.get_allocated_height()))
        context.set_operator(cairo.OPERATOR_SOURCE)
        context.set_source_rgba(0, 0, 0, 0)
        context.paint()
        context.set_operator(cairo.OPERATOR_OVER)
        pad = 22
        track = max(20, width - pad * 2)
        cy = height / 2
        context.set_line_cap(cairo.LINE_CAP_ROUND)
        context.set_line_width(4)
        context.set_source_rgba(0, 0, 0, 0.4)
        context.move_to(pad, cy)
        context.line_to(pad + track, cy)
        context.stroke()
        context.set_source_rgba(1, 1, 1, 0.92)
        context.move_to(pad, cy)
        context.line_to(pad + track * self.volume, cy)
        context.stroke()
        knob = pad + track * self.volume
        context.arc(knob, cy, 6.5, 0, 6.2832)
        context.set_source_rgba(0, 0, 0, 0.55)
        context.fill()
        context.arc(knob, cy, 5, 0, 6.2832)
        context.set_source_rgba(1, 1, 1, 0.96)
        context.fill()
        return True

    def _volume_at(self, x: float) -> float:
        width = max(1, int(self.slider.get_allocated_width()))
        pad = 22
        track = max(20, width - pad * 2)
        return min(1.0, max(0.0, (float(x) - pad) / track))

    def _set_volume(self, value: float) -> None:
        self.volume = min(1.0, max(0.0, float(value)))
        self.cfg["volume"] = self.volume
        try:
            self.player.set_property("volume", self.volume)
        except Exception:
            pass
        if self._hissing and self.hiss_vol is not None:
            self.hiss_vol.set_property("volume", 0.05 * self.volume)
        self.slider.queue_draw()
        self._persist()

    def _slider_press(self, _widget, event) -> bool:
        if int(event.button) == 3:
            self._popup_menu(event)
            return True
        if int(event.button) != 1:
            return False
        width = int(self.slider.get_allocated_width())
        height = int(self.slider.get_allocated_height())
        name = ""
        if float(event.x) <= GRIP:
            name = "west"
        elif float(event.x) >= width - GRIP:
            name = "east"
        if float(event.y) >= height - GRIP:
            name = {"west": "south-west", "east": "south-east"}.get(name, "south")
        if name:
            ox, oy = self.get_position()
            ow, oh = self.get_size()
            self._resize = {
                "nick": name,
                "xr": float(event.x_root),
                "yr": float(event.y_root),
                "ox": int(ox),
                "oy": int(oy),
                "ow": int(ow),
                "oh": int(oh),
            }
            _gestures.add(id(self))
            self.placement.note_press()
            return True
        self._vol_drag = True
        self._set_volume(self._volume_at(event.x))
        return True

    def _slider_motion(self, widget, event) -> bool:
        if self._resize is not None:
            gesture = self._resize
            dx = int(round(float(event.x_root) - gesture["xr"]))
            dy = int(round(float(event.y_root) - gesture["yr"]))
            x, y, w, h = apply_rect(
                gesture["nick"],
                gesture["ox"],
                gesture["oy"],
                gesture["ow"],
                gesture["oh"],
                dx,
                dy,
                MIN_W,
                MIN_PH + BAR,
                False,
            )
            x, y, w, h = fit_aspect(
                x, y, w, h, gesture["nick"], gesture["ox"], gesture["oy"], gesture["ow"], gesture["oh"]
            )
            self.cfg["x"], self.cfg["y"], self.cfg["w"], self.cfg["h"] = x, y, w, h
            self.resize(w, h)
            self.move(x, y)
            return True
        if self._vol_drag:
            self._set_volume(self._volume_at(event.x))
            return True
        width = int(widget.get_allocated_width())
        height = int(widget.get_allocated_height())
        name = edge_name_at(float(event.x), float(event.y), width, height, GRIP)
        cursor_name = "default"
        if name in ("west", "east"):
            cursor_name = "ew-resize"
        elif name in ("south",):
            cursor_name = "ns-resize"
        elif name in ("south-west", "north-east"):
            cursor_name = "nesw-resize"
        elif name in ("south-east", "north-west"):
            cursor_name = "nwse-resize"
        display = self.get_display()
        gdk_window = widget.get_window()
        if display is not None and gdk_window is not None:
            gdk_window.set_cursor(Gdk.Cursor.new_from_name(display, cursor_name))
        return False

    def _slider_release(self, _widget, event) -> bool:
        if self._resize is not None:
            self._resize = None
            _gestures.discard(id(self))
            self.placement.note_geometry_change()
            self._persist()
        self._vol_drag = False
        return int(getattr(event, "button", 0)) == 1

    def _constrain(self, x, y, w, h, edge, ox, oy, ow, oh):
        nick = edge_nick(edge)
        fitted = fit_aspect(x, y, w, h, nick, ox, oy, ow, oh)
        self.cfg["x"], self.cfg["y"], self.cfg["w"], self.cfg["h"] = fitted
        return fitted

    def _on_gesture_done(self) -> None:
        w, h = self.get_size()
        x, y = self.get_position()
        self.cfg["x"], self.cfg["y"] = int(x), int(y)
        self.cfg["w"], self.cfg["h"] = int(w), int(h)
        self._sync_free_shadow()

    def _on_picture_click(self, _widget, _event, _hit) -> None:
        self._tune_next()

    def _on_button(self, _widget, event) -> bool:
        if int(event.button) == 3:
            self._popup_menu(event)
            return True
        return False

    def _on_scroll(self, _widget, event) -> bool:
        dy = 0.0
        if event.direction == Gdk.ScrollDirection.UP:
            dy = -1.0
        elif event.direction == Gdk.ScrollDirection.DOWN:
            dy = 1.0
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            dy = float(event.delta_y)
        if abs(dy) < 0.01:
            return False
        now = time.monotonic()
        if now - self._scroll_at < 0.07:
            return True
        self._scroll_at = now
        self._resize_by(96 if dy < 0 else -96)
        return True

    def _resize_by(self, delta: int) -> None:
        x, y = self.get_position()
        w, h = self.get_size()
        cx = x + w / 2
        cy = y + h / 2
        nx, ny, nw, nh = fit_aspect(int(x), int(y), int(w) + int(delta), int(h), "east", int(x), int(y), int(w), int(h))
        nx = int(round(cx - nw / 2))
        ny = int(round(cy - nh / 2))
        self.cfg["x"], self.cfg["y"], self.cfg["w"], self.cfg["h"] = nx, ny, nw, nh
        self._shadow_for = None
        self.resize(nw, nh)
        self.move(nx, ny)
        self.placement.note_geometry_change()

    def _set_picture_width(self, picture_w: int) -> None:
        x, y = self.get_position()
        w, h = self.get_size()
        cx = x + w / 2
        cy = y + h / 2
        nx, ny, nw, nh = fit_aspect(int(x), int(y), int(picture_w), int(h), "east", int(x), int(y), int(w), int(h))
        nx = int(round(cx - nw / 2))
        ny = int(round(cy - nh / 2))
        self.cfg["x"], self.cfg["y"], self.cfg["w"], self.cfg["h"] = nx, ny, nw, nh
        self._shadow_for = None
        self.resize(nw, nh)
        self.move(nx, ny)
        self.placement.note_geometry_change()

    def _on_key(self, _widget, event) -> bool:
        key = int(event.keyval)
        if key == Gdk.KEY_Right:
            self._tune_next()
        elif key == Gdk.KEY_Left:
            self._tune_prev()
        elif key == Gdk.KEY_Up:
            self._set_volume(self.volume + 0.05)
        elif key == Gdk.KEY_Down:
            self._set_volume(self.volume - 0.05)
        elif key == Gdk.KEY_Escape:
            self._to_static()
        else:
            return False
        return True

    def _popup_menu(self, event) -> None:
        menu = Gtk.Menu()
        grouped: dict[str, list[tuple[int, dict]]] = {name: [] for name in GROUP_ORDER}
        for index, channel in enumerate(CHANNELS):
            grouped.setdefault(str(channel["group"]), []).append((index, channel))
        for group in grouped:
            rows = grouped[group]
            if not rows:
                continue
            parent = Gtk.MenuItem.new_with_label(group)
            sub = Gtk.Menu()
            for index, channel in rows:
                label = f"{index + 1:02d}   {channel['name']}"
                item = Gtk.MenuItem.new_with_label(label)
                if index == self.channel:
                    child = item.get_child()
                    if isinstance(child, Gtk.Label):
                        child.set_markup(f"<b>{GLib.markup_escape_text(label)}</b>")
                item.connect("activate", lambda _item, number=index: self._tune(number))
                sub.append(item)
            parent.set_submenu(sub)
            menu.append(parent)
        menu.append(Gtk.SeparatorMenuItem())
        static = Gtk.MenuItem.new_with_label("Static")
        static.connect("activate", lambda *_a: self._to_static())
        menu.append(static)
        menu.append(Gtk.SeparatorMenuItem())
        for name, width in (("720", 1280), ("1080", 1920)):
            item = Gtk.MenuItem.new_with_label(name)
            item.connect("activate", lambda _item, picture=width: self._set_picture_width(picture))
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        login = Gtk.CheckMenuItem.new_with_label("Open at login")
        login.set_active(autostart_enabled())
        login.connect("toggled", lambda item: set_autostart(bool(item.get_active())))
        menu.append(login)
        quit_item = Gtk.MenuItem.new_with_label("Quit")
        quit_item.connect("activate", lambda *_a: self._quit())
        menu.append(quit_item)
        menu.show_all()
        menu.popup_at_pointer(event)
        self._menu = menu

    def _show_snow(self, text: str) -> None:
        self._status = text
        self.snow.show()
        self.snow.queue_draw()

    def _hide_snow(self) -> None:
        self.snow.hide()

    def _hiss(self, on: bool) -> None:
        if self.hiss is None:
            return
        self._hissing = bool(on)
        if on and self.volume > 0:
            self.hiss_vol.set_property("volume", 0.05 * self.volume)
            self.hiss.set_state(Gst.State.PLAYING)
        else:
            self.hiss.set_state(Gst.State.NULL)

    def _on_source(self, _playbin, source) -> None:
        if source.find_property("user-agent"):
            source.set_property("user-agent", UA)
        if source.find_property("timeout"):
            try:
                source.set_property("timeout", 8)
            except Exception:
                pass
        if source.find_property("ssl-strict"):
            try:
                source.set_property("ssl-strict", False)
            except Exception:
                pass

    def _tune_next(self) -> None:
        nxt = 0 if self.channel < 0 else (self.channel + 1) % len(CHANNELS)
        self._tune(nxt)

    def _tune_prev(self) -> None:
        nxt = len(CHANNELS) - 1 if self.channel <= 0 else self.channel - 1
        self._tune(nxt)

    def _tune(self, index: int) -> bool:
        if not self._alive:
            return False
        index = int(index) % len(CHANNELS)
        self.token += 1
        token = self.token
        self.channel = index
        self.cfg["channel"] = index
        channel = CHANNELS[index]
        number = f"{index + 1:02d}"
        self._show_snow(f"{number}   {channel['name']}")
        self._snow_until = time.monotonic() + STATIC_MS / 1000
        self.player.set_state(Gst.State.NULL)
        self._hiss(True)
        self._persist()
        log(f"tune {number} {channel['name']}")
        GLib.timeout_add(STATIC_MS, self._start_channel, token, index)
        return False

    def _start_channel(self, token: int, index: int) -> bool:
        if token != self.token or not self._alive:
            return False
        channel = CHANNELS[index]
        self._hiss(False)
        self.player.set_property("uri", channel["url"])
        self.player.set_property("volume", self.volume)
        result = self.player.set_state(Gst.State.PLAYING)
        if result == Gst.StateChangeReturn.FAILURE:
            self._no_signal(token)
            return False
        GLib.timeout_add(GIVE_UP_MS, self._give_up, token)
        return False

    def _reveal(self, token: int) -> bool:
        if token != self.token or not self._alive:
            return False
        wait = self._snow_until - time.monotonic()
        if wait > 0:
            GLib.timeout_add(int(wait * 1000) + 1, self._reveal, token)
            return False
        self._hiss(False)
        self._hide_snow()
        log(f"locked {CHANNELS[self.channel]['name']}")
        return False

    def _no_signal(self, token: int) -> None:
        if token != self.token or not self._alive:
            return
        try:
            self.player.set_state(Gst.State.NULL)
        except Exception:
            pass
        name = CHANNELS[self.channel]["name"] if 0 <= self.channel < len(CHANNELS) else ""
        number = f"{self.channel + 1:02d}" if self.channel >= 0 else ""
        self._show_snow(f"{number}   No signal" if number else "No signal")
        self._hiss(True)
        log(f"no signal {name}")

    def _give_up(self, token: int) -> bool:
        if token != self.token or not self.snow.get_visible():
            return False
        self._no_signal(token)
        return False

    def _to_static(self) -> None:
        self.token += 1
        self.channel = -1
        self.cfg["channel"] = -1
        try:
            self.player.set_state(Gst.State.NULL)
        except Exception:
            pass
        self._show_snow("")
        self._hiss(True)
        self._persist()
        log("static")

    def _on_bus(self, _bus, message) -> None:
        kind = message.type
        token = self.token
        if kind == Gst.MessageType.STREAM_START:
            GLib.idle_add(self._reveal, token)
        elif kind == Gst.MessageType.ERROR:
            err, _debug = message.parse_error()
            log(f"play {err.message}")
            GLib.idle_add(self._no_signal, token)
        elif kind == Gst.MessageType.EOS:
            GLib.idle_add(self._no_signal, token)

    def _quit(self) -> None:
        if not self._alive:
            return
        self._alive = False
        self.token += 1
        try:
            self.player.set_state(Gst.State.NULL)
        except Exception:
            pass
        self._hiss(False)
        release_pid()
        if self.get_realized():
            self.destroy()
        Gtk.main_quit()

    def _on_destroy(self, *_args) -> None:
        if not self._alive:
            return
        self._alive = False
        self.token += 1
        try:
            self.player.set_state(Gst.State.NULL)
        except Exception:
            pass
        self._hiss(False)
        release_pid()
        Gtk.main_quit()


def self_test() -> int:
    def ratio_ok(rect: tuple[int, int, int, int]) -> bool:
        picture_h = rect[3] - BAR
        return picture_h > 0 and abs(picture_h / rect[2] - 9 / 16) < 0.01

    east = fit_aspect(10, 20, 800, 400, "east", 10, 20, 640, 400)
    if not ratio_ok(east):
        print("east aspect", east)
        return 1
    west = fit_aspect(10, 20, 800, 400, "west", 10, 20, 640, 396)
    if west[0] + west[2] != 10 + 640 or not ratio_ok(west):
        print("west edge moved", west)
        return 1
    south = fit_aspect(0, 0, 640, 500, "south", 0, 0, 640, 400)
    if south[1] != 0 or not ratio_ok(south):
        print("south aspect", south)
        return 1
    small = fit_aspect(0, 0, 100, 100, "east", 0, 0, 100, 100)
    if small[2] < MIN_W or small[3] != int(round(small[2] * 9 / 16)) + BAR and small[3] < MIN_PH + BAR:
        print("min size", small)
        return 1
    full = default_window(1993, 1248)
    if full != (1920, 1080 + BAR):
        print("1080 fit", full)
        return 1
    tight = default_window(900, 600)
    if tight[0] < MIN_W or tight[1] <= BAR or (tight[1] - BAR) * 16 != tight[0] * 9 and abs((tight[1] - BAR) / tight[0] - 9 / 16) > 0.02:
        print("tight fit", tight)
        return 1
    left, right, top, bottom = free_insets(1920, 1116, 55, 32)
    if left < 55 or top < 32 or left + right > 1920 // 2 or top + bottom > 1116 // 2:
        print("insets", left, right, top, bottom)
        return 1
    names = [channel["name"] for channel in CHANNELS]
    groups = {channel["group"] for channel in CHANNELS}
    if len(names) != len(set(names)) or groups != set(GROUP_ORDER):
        print("channels", len(names), groups)
        return 1
    if any(".m3u8" not in channel["url"] and ".mpd" not in channel["url"] for channel in CHANNELS):
        print("channel urls")
        return 1
    if Gst.ElementFactory.make("playbin", None) is None or Gst.ElementFactory.make("appsink", None) is None:
        print("gstreamer elements missing")
        return 1
    if Gst.ElementFactory.make("hlsdemux", None) is None:
        print("hlsdemux missing")
        return 1
    print(f"ok {len(CHANNELS)} channels, 1920x1080 picture, bar {BAR}")
    return 0


def main() -> None:
    replace = "--replace" in sys.argv
    if "--self-test" in sys.argv:
        Gst.init(None)
        raise SystemExit(self_test())
    Gst.init(None)
    claim_pid(replace)
    install_launchers()
    pin_panel()
    window = TVWindow(load_cfg())
    window.show_all()
    if int(window.channel) < 0:
        window.snow.show()
    Gtk.main()


if __name__ == "__main__":
    main()
