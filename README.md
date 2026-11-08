# ✦ fancy_terminal

A frameless, neon-styled desktop terminal for Windows (works on macOS/Linux too) — built with Python + PyQt6. Not a wrapper around cmd/PowerShell, but a custom command runner with a proper shell feel: tabs, history, aliases, working `cd`, Linux-style file tools, ASCII system stats on startup, and a voxel shockwave that fires from the last word every time you hit Enter.

```
  ╔═╗╔═╗╔╗╔╔═╗╦ ╦ ╔╦╗╔═╗╦═╗╔╦╗╦╔╗╔╔═╗╦
  ╠╣ ╠═╣║║║║  ╚╦╝  ║ ╠═╣╠╦╝║║║║║║║╠═╣║
  ╚  ╩ ╩╝╚╝╚═╝ ╩   ╩ ╚═╝╩╚═╩ ╩╩╝╚╝╩ ╩╩═╝
```

<!-- Replace with an actual screenshot: assets/screenshot.png -->
<p align="center">
  <img src="assets/screenshot.png" alt="fancy_terminal screenshot" width="820">
</p>

---

## Features

### Visual
- **Frameless, rounded window** — custom title bar with drag-to-move, invisible resize zone on every edge, neon minimize / maximize / close buttons.
- **Voxel shockwave** — a 2D pixel-grid pulse fires from the center of the last word on every Enter. Sharp bright wavefront, exponential wake, dims continuously as it expands, then fades out.
- **Typewriter output** — every line types itself in, character by character. Adaptive speed: slow and readable for short output, instantly flushed for big dumps (`dir /s`, `npm install`, etc.).
- **ANSI color support** — real color parsing for `git status`, `npm --help`, `ls --color` and friends. Non-SGR escape sequences are stripped so output stays clean.
- **Glowing input** — subtle pulsing cyan border while focused.
- **Startup system banner** — greeting, OS / Python / host / cwd, plus ASCII progress bars for CPU, GPU and RAM usage.

### Functional
- **Tab completion** — commands *and* file paths, case-insensitive, cached PATH scan.
- **History** — ↑ / ↓ navigation, `!!` / `!n` / `!-n` expansion, **Ctrl+R** incremental reverse search.
- **Shell builtins** — `cd`, `pwd`, `history`, `alias`, `export`, `unset`, `echo`, `clear`, `exit`, `demo`.
- **Linux tools on Windows** — `ls`, `cat`, `touch`, `mkdir`, `rmdir`, `rm`, `cp`, `mv`, `which`/`type`, `whoami`, `uname`, `env`, `date`, `df`, `du`, `head`, `tail`, `wc`, `grep`, `find`, `tree`.
- **Wildcards** — `ls *.py`, `cat *.txt`.
- **Path convenience** — `cd` accepts quotes, mixed slashes, `~`, and shortcuts `..`, `...`, `~`, `-`.
- **Ctrl+C** interrupts a running command without closing the app.
- **Exit-code + duration** footer after every shell command (`[exit 0] · 0.34s`).

---

## Requirements

- **Python 3.9+**
- **PyQt6**

Optional (for live CPU / GPU / RAM stats in the startup banner):

- **`psutil`** — CPU + RAM (any OS)
- **`gputil`** — NVIDIA GPU via `nvidia-smi` (falls back to `pynvml`, then to Windows `Get-Counter` for AMD/Intel)

If the optional packages are missing, the banner simply shows `n/a` for those bars. Everything else works.

---

## Install

```bash
git clone https://github.com/<your-user>/fancy_terminal.git
cd fancy_terminal

# (recommended) virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# core
pip install PyQt6

# optional system stats
pip install psutil gputil
```

On Windows you may need to use `py` instead of `python`.

---

## Run

```bash
python fancy_terminal.py
```

If Python isn't on your PATH:

```powershell
py fancy_terminal.py
```

The window opens frameless, with the ASCII logo drawn instantly and the greeting typing out below it.

---

## Usage

Just type. Hit **Enter** to run. Every command either matches a builtin, a Linux-tool shim, or falls through to a real shell (`shell=True`, so pipes, redirection, and `&&` work natively).

### Example

```
λ ls -la
drwxr-xr-x         0  Desktop/
-rw-r--r--      2048  notes.txt
-rw-r--r--   1048576  fancy_terminal.py

λ cd "C:\Users\Me\My Folder"
λ pwd
C:\Users\Me\My Folder

λ grep TODO *.py
fancy_terminal.py:42:# TODO: add PTY support

λ tree -L 2
.
├── assets/
│   └── screenshot.png
├── fancy_terminal.py
└── README.md

1 directory, 3 files
```

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Tab` | Complete command / path (case-insensitive) |
| `↑` / `↓` | Navigate history |
| `Ctrl+R` | Reverse-search history (press again to cycle) |
| `Ctrl+C` | Interrupt running command |
| `Ctrl+L` | Clear screen |
| `Ctrl+U` | Clear current line |
| `Ctrl+W` | Delete word backwards |
| `Ctrl+K` | Delete to end of line |
| `Ctrl+D` | Exit (only when input is empty) |
| Drag title bar | Move window |
| Drag window edge | Resize (invisible ~16 px grab zone) |
| Double-click title bar | Toggle maximize |

---

## Built-in commands

| Command | Effect |
|---|---|
| `help` / `?` | Show command overview |
| `cd [dir]` | Change directory (persists, accepts quotes, `~`, `/` or `\`) |
| `pwd` | Print current directory |
| `history` | Numbered command history |
| `alias` | List aliases |
| `alias name=value` | Define alias (e.g. `alias gs=git status`) |
| `export K=V` | Set environment variable |
| `unset K` | Remove environment variable |
| `echo …` | Print arguments |
| `demo` | Showcase the animated progress bars |
| `clear` | Clear output |
| `exit` | Quit |

### Shortcuts

| Input | Effect |
|---|---|
| `..` | `cd ..` |
| `...` | `cd ../..` |
| `~` | Go home |
| `-` | `cd -` (previous directory) |
| `!!` | Re-run last command |
| `!n` | Re-run the n-th command |
| `!-n` | Re-run the command n steps back |

---

## Customization

### Colors & palette

All colors live in `FancyTerminal.__init__` and inline stylesheets. The accent colors are:

- **cyan** `#00d9c8` — prompt, echo, success
- **violet** `#8060d0` — errors, aliases, secondary emphasis
- **steel** `#b8c8d4` — default text
- **dim** `#6f8898` — muted meta text

Replace them with a search-and-replace in the file.

### Ripple tuning

`VoxelRipple` class attributes:

```python
class VoxelRipple(QWidget):
    BLUR_SCALE     = 2      # 1 = sharp pixels, 4 = very soft
    WAKE_DECAY     = 0.55   # higher = longer glowing wake
    WAKE_STRENGTH  = 0.65   # brighter interior
    EDGE_SHARPNESS = 1.6    # tighter bright wavefront
    EDGE_BOOST     = 0.55   # how much extra at the rim
    WAVE_VARIANCE  = 0.10   # per-voxel texture (0 = smooth)
    TRAVEL_DIM     = 0.65   # dims as it reaches the edge
    FADE_RATE      = 0.06
```

| Want | Change |
|---|---|
| Solid glowing sphere | `WAKE_DECAY=0.9`, `WAKE_STRENGTH=0.85`, `EDGE_BOOST=0.35` |
| Comet / shockwave | `WAKE_DECAY=0.25`, `EDGE_SHARPNESS=3.0` |
| Sharp pixel grid | `BLUR_SCALE=1` |
| Organic scatter | `WAVE_VARIANCE=0.3` |

### Adding your own builtin

1. Define a method `_cmd_foo(self, args)` inside `FancyTerminal`.
2. Register it in `_try_linux_builtin`:

```python
fns = {
    ...
    'foo': self._cmd_foo,
}
```

The method receives a list of arguments (already split respecting quotes) and should return `True` to indicate it handled the command.

### Adding an alias automatically

Edit the default dict in `__init__`:

```python
self._aliases = {
    'll': 'ls -la',
    'la': 'ls -a',
    'l':  'ls',
    'gs': 'git status',   # your addition
}
```

---

## Known limitations

- **No PTY** — interactive programs (`python` REPL, `ssh`, `vim`, `top`, `nano`, password prompts) don't work. The app runs each command through `subprocess.Popen(shell=True)` without a pseudo-terminal, so child processes see a pipe, not a TTY. `QTermWidget` or a `pyte` + `pywinpty` stack would be the upgrade path.
- **Single command at a time** — while a command is running, sending another queues it. `Ctrl+C` interrupts.
- **Windows-only for GPU fallback** — the `Get-Counter` PowerShell probe is Windows-specific. On Linux/macOS the code relies on `gputil`/`pynvml`.
- **No scrollback cap** — very long outputs (millions of lines) will grow memory. Wrap the typewriter in a ring buffer if you need to cap it.

---

## How it works

A single file, ~1200 lines. Highlights:

| Component | Role |
|---|---|
| `FancyTerminal` (QWidget) | Main window: layout, resize logic, keyboard, command dispatch |
| `TitleBar` + `WinButton` | Custom frameless chrome |
| `VoxelRipple` | Full-window overlay that draws the ripple |
| `GlowInput` | Pulsing focus border |
| `Typewriter` | Queue + adaptive drain rate, groups same-color runs |
| `ShellWorker` (QThread) | Runs commands without blocking the UI, supports kill |
| `SmoothBar` / `ProgressGroup` | Bottom horizontal progress bars |
| `parse_ansi` | SGR → hex color conversion, strips other escapes |

The ripple is rendered at 1/2 resolution into a `QImage` and upscaled with `SmoothPixmapTransform`, so it stays soft at any window size and cheap to paint.

---

## Roadmap

- [ ] PTY support (interactive programs)
- [ ] Split panes / tabs
- [ ] Persistent settings (`~/.fancy_terminal.json`)
- [ ] Theme switcher
- [ ] Drag-and-drop file into terminal → inserts path
- [ ] `Ctrl+Shift+C/V` for copy/paste on any OS

---

## License

MIT — see [LICENSE](LICENSE).

---

## Credits

Built with **PyQt6**. Inspired by iTerm2, Windows Terminal, and the pixel-grid aesthetic of early demoscene intros.