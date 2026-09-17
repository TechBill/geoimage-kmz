# AGENTS.md

Notes for AI coding agents (Claude Code, etc.) working in this repo. This is
project-specific operational knowledge that isn't obvious from reading the
code alone — read this before touching build/version/icon code.

## What this project is

A single-file Tkinter desktop app (Python 3.12) that turns a map image plus
a handful of user-picked control points (pixel ↔ lat/lon pairs) into a
Google Earth KMZ ground overlay, fitting a best-fit affine transform via
`numpy.linalg.lstsq`. Everything lives in
[`geoimage_kmz.py`](geoimage_kmz.py) — no `src/` layout, no
`requirements.txt`, no test suite. Packaged as a standalone app with
PyInstaller via `GeoImage KMZ.spec` (one spec file, branches internally for
Windows vs macOS).

## Building the standalone app

```bash
python -m PyInstaller --noconfirm --clean "GeoImage KMZ.spec"
```

The spec detects platform at build time (`sys.platform`) and branches:

- **macOS**: onedir `COLLECT` + `BUNDLE` → `dist/GeoImage KMZ.app` (icon
  from `assets/icon.icns`).
- **Windows**: onefile `EXE` → `dist/GeoImage KMZ.exe` (icon from
  `assets/icon.ico`, also bundled as a data file into `_MEIPASS/assets/`
  since the app re-loads it at runtime via `iconbitmap()` — see below).

There's no cross-compiling: the spec must be run **on** the target platform
(a Windows box for the `.exe`, a Mac for the `.app`). This repo currently
only has a macOS build actually produced/tested.

`build/` and `dist/` are gitignored — nothing there is source of truth.

## Version numbers — where they live (and where they don't)

- `geoimage_kmz.py` → `__version__` near the top of the file (drives
  `APP_TITLE`, shown in the Tk window title bar).
- `GeoImage KMZ.spec` → `CFBundleShortVersionString` / `CFBundleVersion` in
  the `BUNDLE(... info_plist=...)` block — **macOS only**. Verify post-build
  with:
  ```bash
  /usr/libexec/PlistBuddy -c "Print CFBundleShortVersionString" "dist/GeoImage KMZ.app/Contents/Info.plist"
  ```
- **Windows has no equivalent.** The Windows `EXE(...)` block has no
  `version=` argument, so the built `.exe` carries no FileVersion/
  ProductVersion resource — Explorer's "Properties → Details" tab will show
  nothing useful. If that's ever needed, it requires a PyInstaller
  version-info file (`pyi-grab_version` / `pyi-set_version`) wired into the
  spec; nothing like that exists today.

Nothing enforces these stay in sync — bump `__version__` and both
`info_plist` strings together by hand, and grep for the old version string
before calling a bump done.

## Windows icon: two separate code paths, easy to break one without noticing

Icon handling is duplicated because Windows needs the taskbar/title-bar icon
set at *runtime*, whereas macOS gets it for free from the `.app` bundle's
`Info.plist`/`.icns` at *build* time:

- Build-time (`GeoImage KMZ.spec`): bundles `assets/icon.ico` as a data file
  under `assets/` in the frozen app, and separately passes it as
  `EXE(icon=...)` for the exe's own icon resource — two different
  mechanisms, both need to keep pointing at the same file.
- Run-time (Windows only, top of `GeoImageKMZApp.__init__`): calls
  `self.iconbitmap(...)`, resolving the path via `sys._MEIPASS` when frozen
  (`getattr(sys, "frozen", False)`) vs the relative path `"assets/icon.ico"`
  when run from source — which only works if the process's cwd is the repo
  root. Both branches are wrapped in a bare `except Exception: pass`, so a
  wrong path (renamed `assets/` folder, changed bundle destination, wrong
  cwd) fails silently instead of erroring. A clean build log does not mean
  the icon actually loaded — check visually after any packaging change.

## PLSS lookup hits live government GIS servers — synchronous, blocks the UI

`query_missouri_plss_section()` / `query_kansas_plss_section()`
(`urllib.request.urlopen`, 10s timeout, via the shared `_fetch_plss_json()`
helper) run directly on the Tk main thread from
`PLSSLookupDialog.fetch_coordinates()`. The cursor changes to "watch" but
the whole app is frozen until the request returns or times out — that's
inherent to the current implementation, not a regression if you see it.
Endpoints are third-party (`gis.mo.gov`, `wfs.ksdot.org`); if either changes
its schema, a genuine schema mismatch surfaces as an empty `features` list
(→ `None` return → "No section found" dialog) rather than crashing — check
the `where`-clause field names in `extract_corner_coordinate()` /
`query_*_plss_section()` first if a lookup that used to work stops working
(Missouri uses `TWP_NUM`/`TWP_DIR`/`RNG_NUM`/`RNG_DIR`/`SEC_NUM`; Kansas uses
zero-padded string fields `Township`/`Range`/`Section` like
`"01S"`/`"41W"`/`"05"`).

### Connection/SSL failures are a *separate* error path from "no match"

As of v2.2, `_fetch_plss_json()` raises `PLSSConnectionError` (not a silent
`None`) for anything that isn't a clean round-trip: `URLError` (DNS/network
failure or, if `e.reason` is an `ssl.SSLError`, a cert-verification
failure), `socket.timeout`, or any other exception while fetching/parsing.
`query_missouri_plss_section()` / `query_kansas_plss_section()` only return
`None` for a request that actually reached the server and got zero matching
features back — that's the one case that should show "No section found".
`fetch_coordinates()` catches `PLSSConnectionError` separately from the
generic `Exception` handler and shows a "Connection Error" dialog instead.
**Do not collapse this back into a bare `except Exception: return None`** —
that's the exact bug this fixes (a real-world case: a dev machine's
python.org install had never run "Install Certificates.command", so every
HTTPS request raised `SSLCertVerificationError`, which the old code
swallowed and reported as "No section found: T40N R27W S5" even though that
section exists and the service was working fine — confirmed by hitting the
ArcGIS endpoint directly with curl).

### Self-healing TLS trust store for distributed copies of the app

Because this is a standalone app that gets copied to other people's
computers, it can't assume the target machine's Python/OS certificate store
is set up correctly (this is a known failure mode for python.org Python on
macOS, and frozen PyInstaller apps in general don't inherit a system trust
store the way a browser does). `_get_ssl_context()` builds the SSL context
used for every PLSS request from `certifi.where()` instead of the system
default, so the app carries its own known-good CA bundle rather than
depending on whatever's (or isn't) on the host machine. `GeoImage KMZ.spec`
bundles `certifi`'s package data via `collect_all("certifi")` alongside
NumPy/Pillow specifically so this works in the frozen build, not just when
run from source with certifi pip-installed. If `certifi` is unavailable for
some reason, `_get_ssl_context()` falls back to `ssl.create_default_context()`
(the old, host-dependent behavior) — don't remove that fallback, but also
don't rely on it: the whole point of bundling certifi is to not need it.

## Nothing persists between runs

`last_image_dir`, `last_kmz_dir`, `last_points_dir`, and all `last_plss_*`
fields (remembered PLSS form values) are plain instance attributes on
`GeoImageKMZApp`, reset to defaults (`~/Desktop`, "Missouri", etc.) on every
launch. There is no config file anywhere in this app — no
`~/Library/Application Support`, no `%APPDATA%`. Don't assume a setting
"should" survive a restart; it never has.

### `last_plss_corner` is auto-advanced, not just remembered

As of v2.3, a successful fetch in `PLSSLookupDialog.fetch_coordinates()`
stores `_next_plss_corner(corner)` into `self.app.last_plss_corner`, not the
corner that was just used. `PLSS_CORNER_ORDER = ["NW", "NE", "SE", "SW"]`
defines the clockwise cycle (top-left, top-right, bottom-right, bottom-left,
back to top-left); `_next_plss_corner()` wraps with `% len(...)`. The intent
is a workflow where a user walks all four corners of one section (or several
adjacent sections) without re-selecting Corner each time — reopening the
dialog after fetching NW pre-selects NE, and so on. This still resets on
app restart along with every other `last_plss_*` field (see above) — it's
an in-session convenience, not a persisted preference. If you touch the
corner combobox values/labels, keep `PLSS_CORNER_LABELS` (keyed the same as
`PLSS_CORNER_ORDER`) as the single source of truth for both the dropdown
and the auto-advance logic rather than hardcoding the list again.

## Testing without a full app run

There's no test suite (`unittest`/`pytest`) and no headless CI. For UI
changes, just run it from source:

```bash
python3 geoimage_kmz.py
```

To sanity-check the *built* app launches cleanly on macOS:

```bash
open "dist/GeoImage KMZ.app"
sleep 3 && ps aux | grep -i "GeoImage KMZ" | grep -v grep   # confirm it's running
osascript -e 'tell application "GeoImage KMZ" to quit'      # clean shutdown
```

(No assistive-access permission in this environment for window-level
screenshots — process presence + clean quit is the practical liveness
check.)

## Misc

- Dependencies are just Pillow and NumPy. The `numpy` import is wrapped in
  `try/except` and gated by `_require_numpy()` before KMZ generation — the
  app otherwise runs fine without NumPy, it just can't generate a KMZ.
  There's no `requirements.txt`; the docstring at the top of
  `geoimage_kmz.py` is the only place dependencies are documented
  (`python3 -m pip install pillow numpy`).
- `notes.txt` is not a changelog or TODO list — it's a one-line reminder of
  the PyInstaller build command.
- Loading a new image, or rotating the current one, clears all control
  points and any border mask (`points.clear()` / `border_points.clear()`).
  This is intentional (pixel coordinates would otherwise no longer line up)
  but is a real data-loss trap if a user rotates after carefully placing
  points — the app does confirm with a dialog first, don't remove that
  confirmation without a replacement safeguard.
