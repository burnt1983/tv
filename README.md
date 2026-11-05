# TV

A borderless 16:9 television for the Linux desktop. There is no bezel. The window around the glass is clear, and the picture stays widescreen at every size.

Click the picture for the next channel. Static stays up until that station locks.

## Install

Needs Python 3, GTK 3, PyGObject, cairo, and GStreamer with the HLS plugin
(`python3-gi`, `gir1.2-gtk-3.0`, `gir1.2-gst-plugins-base-1.0`, `gstreamer1.0-plugins-bad` for `hlsdemux`).

```bash
git clone https://github.com/burnt1983/tv.git
cd tv
bash install.sh
tv
```

The place, size, volume, and last channel are saved in `~/.config/lee-tv/config.json`. It does not start at login until you tick Open at login.

## How to use it

| Action | What happens |
|---|---|
| Click the picture | Next channel |
| Left / Right | Previous / next channel |
| Drag the picture | Moves the window, including over the top bar and the dock |
| Drag an edge, or scroll | Resizes the glass. The picture stays 16:9 |
| Drag the line under the glass | Volume |
| Right-click | Station, Static, 720, 1080, open at login, quit |
| Escape | Back to static |

The right-click menu groups the stations: BBC, Regions, Kids, Entertainment, Shopping, News.

## Channels

Fifty-eight public HLS streams from the broadcasters' own playlists. BBC One is the London feed. ITV, Channel 4, Channel 5, UKTV, and Sky's main channels are DRM-locked and are not listed.

A station can go offline. The glass stays on static until the next one locks.

## Uninstall

```bash
bash uninstall.sh
```

## Licence

MIT. See [LICENSE](LICENSE).
