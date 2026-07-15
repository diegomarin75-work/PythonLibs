# PythonLibs

A collection of Python utility libraries for console output formatting, Snowflake database management, and common helper functions.

---

## Modules

- [`printlib.py`](#printlibpy--printinglibrary-class) — Console printing with ANSI colors, tables, progress bars, and text wrapping.
- [`sfmanager.py`](#sfmanagerpy--snowflakemanager-class) — Snowflake connection lifecycle and SQL query execution.
- [`utils.py`](#utilspy--general-utilities) — Standalone helpers for paths, Git, encoding detection, and more.

---

## `printlib.py` — PrintingLibrary class

Console output library with ANSI color support, spinner/progress-bar animations, volatile (overwrite-in-place) messages, formatted tables, and smart text wrapping.

```python
from printlib import PrintingLibrary

p=PrintingLibrary()
p.Print("Processing files...", Wheel=True)
p.Print("Step 3 of 10", Volatile=True, BarProgress=3, BarLength=10)
p.Print(p.AnsiColor("Success!", p.ANSI_FD_GREEN))
```

### ANSI Color Constants

The class exposes a full set of ANSI color code constants using the naming convention `ANSI_{layer}{shade}_{color}`:

| Prefix | Meaning |
|---|---|
| `FD` | Foreground dark |
| `FB` | Foreground bright |
| `BD` | Background dark |
| `BB` | Background bright |

Available colors: `BLACK`, `RED`, `GREEN`, `YELLOW`, `BLUE`, `MAGENTA`, `CYAN`, `WHITE`.

Example: `ANSI_FD_RED` (dark red foreground=31), `ANSI_BB_CYAN` (bright cyan background=106).

### Constructor

#### `__init__()`

Initializes internal state: message counter, progress-bar step, last-output tracking, and default mode flags (silent mode off, volatile enabled, progress bar enabled).

### Methods

#### `GetConsoleWidth()`

Returns the terminal width in characters. Defaults to `9999` when stdout is not a TTY (e.g. piped output).

- **Returns:** `int`

#### `GetConsoleHeight()`

Returns the terminal height in rows. Defaults to `9999` when stdout is not a TTY.

- **Returns:** `int`

#### `AnsiColor(Text, FgColor, BkColor=None)`

Wraps a string with ANSI escape codes for colorized output.

- **Text** (`str`): The text to colorize.
- **FgColor** (`int`): Foreground color code (use one of the `ANSI_F*` constants).
- **BkColor** (`int | None`): Optional background color code (use one of the `ANSI_B*` constants).
- **Returns:** `str` — text wrapped in ANSI escape sequences, automatically reset at the end.

```python
p.AnsiColor("Error!", p.ANSI_FD_RED)
p.AnsiColor("Highlight", p.ANSI_FD_WHITE, p.ANSI_BD_BLUE)
```

#### `SetSilentMode(Enabled)`

Enables or disables silent mode. When enabled, all subsequent calls to `Print()` produce no output.

- **Enabled** (`bool`): `True` to suppress output, `False` to resume.

#### `SetVolatileEnabled(Enabled)`

Enables or disables volatile message rendering. When disabled, calls to `Print()` with `Volatile=True` are silently ignored.

- **Enabled** (`bool`): `True` to allow volatile output, `False` to suppress it.

#### `SetProgbarEnabled(Enabled)`

Enables or disables progress bar rendering inside `Print()`. When disabled, the `BarProgress`/`BarLength` parameters are ignored.

- **Enabled** (`bool`): `True` to render progress bars, `False` to suppress them.

#### `VisibleLength(Value)`

Computes the visible (printed) length of a string by stripping ANSI color codes and OSC 8 hyperlink sequences that occupy no screen space.

- **Value** (`str`): The string to measure.
- **Returns:** `int` — number of visible characters.

#### `FormatParagraph(Text, Width, Indentation=0)`

Word-wraps text to a given width while preserving indentation on continuation lines. Two special Unicode characters control layout:

- `\u00A0` — non-breaking space (prevents wrapping at that position; rendered as a normal space).
- `\uE000` — forced line break (splits text into separate paragraphs).

Parameters:

- **Text** (`str`): The text to wrap.
- **Width** (`int`): Maximum line width.
- **Indentation** (`int`): Number of leading spaces on continuation lines (default `0`).
- **Returns:** `str` — newline-delimited wrapped text.

#### `Print(Text, Wheel=False, Volatile=False, Partial=False, ClassName="", BarProgress=None, BarLength=None)`

The main output method. Prints a formatted line to stdout (or stderr for error classes) with optional decorations.

- **Text** (`str`): Message body.
- **Wheel** (`bool`): Prefix the line with a spinning animation character (`- \ | /`) that cycles on each call.
- **Volatile** (`bool`): Print without a trailing newline so the next output overwrites this line in-place. Useful for real-time status messages.
- **Partial** (`bool`): Like `Volatile` but intended for intermediate progress fragments.
- **ClassName** (`str`): A severity label prepended in square brackets (e.g. `"ERR"`, `"WARN"`). When the class is `ERR`, `ERROR`, `FAIL`, or `FAILURE`, output is directed to stderr.
- **BarProgress** (`int | None`): Explicit number of completed ticks to show in the progress bar.
- **BarLength** (`int | None`): Total tick count that defines the progress bar width. When `BarProgress` is `None` and `BarLength` is set, the bar auto-increments on each call.

```python
p.Print("Connecting...", Wheel=True)
p.Print("Downloading 50%", Volatile=True, BarProgress=5, BarLength=10)
p.Print("Something failed", ClassName="ERR")
```

#### `AddHline(Rows)`

Appends a horizontal separator marker to a row data list. The separator is rendered as a full-width line when passed to `PrintTable()`.

- **Rows** (`list[list[str]]`): The data rows list to append the separator to.

#### `PrintTable(Heading1, Heading2, ColAttributes, Rows, ReturnOutput=False, ConsoleWidth=None)`

Pretty-prints a formatted table with borders, column alignment, word wrapping, and automatic truncation when the table exceeds the terminal width.

- **Heading1** (`list[str]`): Primary header labels (one per column).
- **Heading2** (`list[str] | None`): Optional secondary header row, or `None` to skip.
- **ColAttributes** (`list[str]`): Format codes per column. Each string is a combination of:
  - `L` — Left-align
  - `R` — Right-align
  - `C` — Center-align
  - `M` — Multi-line word-wrap (column is also resizable)
  - `W` — Resizable column (can shrink to fit the terminal)
  - `S` — Split cell content on literal `\n`
  - `A` — ANSI-aware alignment (accounts for invisible escape sequences when padding)
- **Rows** (`list[list[str]]`): Data rows. Insert horizontal dividers with `AddHline()`.
- **ReturnOutput** (`bool`): When `True`, returns a `list[str]` of rendered lines instead of printing.
- **ConsoleWidth** (`int | None`): Override the detected terminal width.
- **Returns:** `list[str] | None`

```python
p.PrintTable(
    ["Name", "Status", "Description"],
    None,
    ["L", "C", "ML"],
    [["server-1", "OK", "Primary application server"],
     ["server-2", "DOWN", "Replica node currently offline"]]
)
```

---

## `sfmanager.py` — SnowflakeManager class

Wraps the Snowflake Python Connector with connection lifecycle management, background library preloading, and SQL execution with debug support.

```python
from sfmanager import SnowflakeManager

sf=SnowflakeManager(PreloadLibraries=True, ConnectionsFile="~/.snowflake/connections.toml")
sf.OpenConnection("my_connection")
ok, msg, rows=sf.ExecuteSqlQuery("SELECT CURRENT_USER()")
sf.CloseConnection()
```

### Constructor

#### `__init__(PreloadLibraries=False, ConnectionsFile=None, ConnParameters=None, Debug=False)`

Creates a new manager instance and optionally starts background preloading of Snowflake libraries.

- **PreloadLibraries** (`bool`): When `True`, Snowflake connector libraries are imported in a background daemon thread so they are ready when the first connection is opened.
- **ConnectionsFile** (`str | None`): Path to a TOML file containing named Snowflake connection definitions.
- **ConnParameters** (`dict | None`): Optional dictionary of connection parameters (e.g. `{"account": "...", "user": "...", "password": "..."}`). When provided, this takes precedence over the connections file.
- **Debug** (`bool`): When `True`, every SQL query is printed and the user is prompted before execution with options: **(y)es** continue, **(n)o** skip, **(a)ll** run all without asking, **(c)ancel** abort all, **(e)rrors only** continue silently but print failures.

### Methods

#### `OpenConnection(ConnectionName=None)`

Opens a Snowflake connection. If the same connection is already open, it is reused. Blocks until background library preloading completes (if enabled).

- **ConnectionName** (`str | None`): Named connection from the connections file, or `None` to use the `ConnParameters` dictionary.
- **Returns:** `tuple[bool, str]` — `(success, message)`.

#### `CloseConnection()`

Closes the current Snowflake connection and resets internal state. Safe to call when no connection is open (no-op).

#### `GetCurrentConnectionName()`

Returns the name of the currently active connection.

- **Returns:** `str | None` — Connection name, or `None` if no connection is open or execution has been cancelled.

#### `ExecuteSqlQuery(Query)`

Executes one or more SQL statements against the active connection.

- **Query** (`str | list[str]`): A single SQL string, or a list of SQL strings to execute sequentially. When a list is provided, results from all statements are combined. Execution stops at the first failure.
- **Returns:** `tuple[bool, str, list[dict] | None]` — `(success, message, results)`. On success, `results` is a list of dictionaries where each dict represents a row with lowercase column names as keys. On failure, `results` is `None`.

In debug mode, each query is printed before execution and the user is prompted to continue, skip, run all, cancel, or switch to errors-only mode.

```python
ok, msg, rows=sf.ExecuteSqlQuery("SELECT name, created_on FROM databases")
if ok:
    for row in rows:
        print(row["name"], row["created_on"])
```

---

## `utils.py` — General Utilities

Standalone helper functions. Import them directly:

```python
from utils import AbsPath, FormatSeconds, JsonFileParser
```

### Functions

#### `GetVersion()`

Reads the tool version string from a `VERSION` file located next to the module.

- **Returns:** `str` — Version string, or `"0.0.0"` if the file cannot be read.

#### `Coalesce(*Args)`

Returns the first argument that is not `None`, similar to SQL `COALESCE`.

- **\*Args**: Variable number of arguments.
- **Returns:** The first non-`None` value, or `None` if all arguments are `None`.

```python
Coalesce(None, None, "default")  # "default"
```

#### `FormatSeconds(TotalSecs)`

Formats a number of seconds into a human-readable duration string.

- **TotalSecs** (`int | float`): Total seconds.
- **Returns:** `str` — Formatted as `"Xh Ym Z.ZZs"`, omitting hours/minutes when zero.

```python
FormatSeconds(3661.5)   # "1h 1m 1.50s"
FormatSeconds(45.123)   # "45.12s"
```

#### `AbsPath(FilePath, RelativeTo=None)`

Converts a path to an absolute, normalized form. On Windows, drive letters are lowercased for consistency.

- **FilePath** (`str`): Input path (may be relative).
- **RelativeTo** (`str | None`): When provided, relative paths are resolved against this directory instead of the current working directory.
- **Returns:** `str` — Normalized absolute path.

```python
AbsPath("data/file.csv", RelativeTo="/home/user/project")
# "/home/user/project/data/file.csv"
```

#### `ExecCommand(Command)`

Executes a shell command and captures its combined stdout/stderr output.

- **Command** (`str`): The command line to run.
- **Returns:** `tuple[int, str]` — `(return_code, output_text)`.

```python
code, output=ExecCommand("git status")
```

#### `GetGitRepoRoot(GitRepo)`

Returns the root directory of the Git repository that contains the given path.

- **GitRepo** (`str`): A path inside (or at the root of) a Git repository.
- **Returns:** `str | None` — Absolute path of the repo root, or `None` if the path is not inside a Git repository.

#### `IsGitRepo(GitRepo)`

Tests whether the given path is inside a Git repository.

- **GitRepo** (`str`): Path to check.
- **Returns:** `bool`

#### `IsFileOnBranch(RepoPath, BranchName, FilePath)`

Checks whether a specific file exists on a remote branch of a Git repository.

- **RepoPath** (`str`): Path to the Git repository.
- **BranchName** (`str`): Branch name (looked up as `origin/<BranchName>`).
- **FilePath** (`str`): File path relative to the repository root.
- **Returns:** `bool`

#### `DetectFileEncoding(FilePath, NumBytes=100000)`

Detects a file's text encoding by sampling bytes and running the `chardet` heuristic.

- **FilePath** (`str`): Path to the file.
- **NumBytes** (`int`): Number of bytes to read for detection (default `100000`).
- **Returns:** `tuple[bool, str, str | None]` — `(success, message, encoding)`. On failure, `encoding` is `None`.

```python
ok, msg, enc=DetectFileEncoding("data.csv")
# (True, "", "utf-8")
```

#### `JsonFileParser(FilePath)`

Parses a JSON configuration file with two extensions beyond standard JSON:

1. Lines starting with `//` are treated as comments and stripped before parsing.
2. Literal newlines inside string values are converted to `\n` escape sequences, allowing multiline strings.

Parameters:

- **FilePath** (`str`): Path to the JSON file.
- **Returns:** `tuple[bool, str, dict | None]` — `(success, message, parsed_object)`. On failure, `parsed_object` is `None`.

```python
ok, msg, config=JsonFileParser("settings.json")
```

---

## Dependencies

- Python 3.11+
- [`chardet`](https://pypi.org/project/chardet/) — used by `utils.py` for file encoding detection.
- [`snowflake-connector-python`](https://pypi.org/project/snowflake-connector-python/) — required only when using `sfmanager.py`.

## License

See the individual project repositories for license information.
