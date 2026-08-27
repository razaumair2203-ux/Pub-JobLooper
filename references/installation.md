# Installation and portability

Joblooper is one self-contained standalone skill. The complete repository—not
only `SKILL.md`—must remain reachable from a Codex skill discovery directory.

## Fresh machine

Authenticate Git only when the repository is private, then clone directly into
the current Codex user-scoped skill location:

```text
git clone https://github.com/razaumair2203-ux/Pub-JobLooper.git ~/.agents/skills/joblooper
cd ~/.agents/skills/joblooper
python jl.py init   # public clone only
python jl.py doctor
```

On Windows PowerShell:

```powershell
git clone https://github.com/razaumair2203-ux/Pub-JobLooper.git "$env:USERPROFILE\.agents\skills\joblooper"
Set-Location "$env:USERPROFILE\.agents\skills\joblooper"
python jl.py init   # public clone only
python jl.py doctor
```

Codex installations that define `CODEX_HOME` can instead use
`$CODEX_HOME/skills/joblooper` (Windows:
`%CODEX_HOME%\skills\joblooper`). Joblooper's installer follows that override;
otherwise it uses `~/.agents/skills/joblooper`.

## Existing clone in another directory

From that clone run:

```text
python tools/install_local_skill.py
```

The installer creates a directory junction on Windows or a symbolic link on
macOS/Linux. This makes the whole checkout discoverable without copying private
data or creating a second runtime state. It refuses to replace an existing
destination.

Use `--dest <path>` when a Codex installation uses a different discovery
directory. The installer never replaces an existing destination.

## Runtime requirements

- Python 3.10 or later is required. Core operation and DOCX generation use only
  the standard library.
- Git credentials are required only for a private repository.
- PDF generation requires Microsoft Word automation on Windows or a
  `libreoffice`/`soffice` executable on Windows, macOS or Linux. DOCX remains
  available when neither PDF engine is installed.
- `PERSONAL_PRIVATE` clones use their governed `.joblooper` directory. A
  `PUBLIC_SKILL` clone defaults to `~/.joblooper`; in a sandbox or shared
  machine, pass `--data-dir` or `JOBLOOPER_DATA_DIR` for an explicit writable,
  private location. `doctor` is read-only and reports an uninitialized runtime.

After installation, start a new Codex turn and invoke `$joblooper`, or rely on
implicit invocation for a matching CV/application request. If it is not listed,
restart Codex and run `python jl.py doctor` from the installed path.

The installed repository includes the complete dashboard. Launch it with
`python jl.py dashboard`. A later launch safely replaces only the registered
Joblooper process, serves the upgraded code at `http://127.0.0.1:8765/`, and
opens that same canonical address. Pull repository upgrades before relaunching;
do not copy dashboard files separately from the skill.
