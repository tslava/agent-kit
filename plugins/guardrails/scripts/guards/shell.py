"""A small, conservative reader for the bash command lines an agent sends to the Bash tool.

It is not a shell. It splits a command line into simple commands and keeps enough
structure for the guards to make a decision:

- quotes, backslashes, comments, `;`, `&&`, `||`, `|`, `&`, newlines, `( )`;
- redirections, here-docs and here-strings;
- `$(...)`, backticks and `<(...)`: the inner command line is read too, because it runs;
- `sh -c`, `bash -c`, `eval`, `env -S`, `xargs`, `find -exec` and common wrappers
  (`env`, `command`, `exec`, `nohup`, `nice`, `time`, `timeout`, `sudo`, `stdbuf`):
  the command they run is read as its own simple command.

Anything whose value is only known at run time (`$VAR`, `$(...)` output, globs) is
marked with UNKNOWN inside the word text. A guard that needs such a value must not
guess: it answers "ask". When the reader cannot follow the structure at all, it adds
a reason to `opaque`.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

UNKNOWN = "\x00"
MAX_DEPTH = 4

_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_REDIR_OPS = ("&>>", "<<<", "<<-", "&>", ">>", "<<", "<&", ">&", "<>", ">|", "<", ">")
_KEYWORDS_SKIP = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "}", "fi", "done", "esac"}
_HEADER_KEYWORDS = {"for", "case", "select", "function"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
_KNOWN_VARS = ("HOME", "TMPDIR")


@dataclass
class Word:
    text: str          # quotes removed; run-time values replaced by UNKNOWN
    glob: bool = False  # has an unquoted *, ? or [

    @property
    def known(self) -> bool:
        return UNKNOWN not in self.text


@dataclass
class Redirect:
    op: str
    fd: str
    target: Word | None


@dataclass
class Simple:
    """One command with its arguments, after wrappers are removed."""
    argv: list[Word]
    assigns: dict[str, Word] = field(default_factory=dict)
    redirects: list[Redirect] = field(default_factory=list)
    stdin_from_pipe: bool = False
    heredoc: str | None = None
    unknown_args: bool = False   # more arguments are added at run time (xargs, find -exec {})
    via: str = ""                # how it was reached: "", "sh -c", "$()", "xargs", "find -exec", ...
    cwd: str | None = None       # None when a `cd` to an unknown place came first

    @property
    def name(self) -> str | None:
        """Program basename, or None if it is only known at run time."""
        if not self.argv:
            return ""
        base = self.argv[0].text.rsplit("/", 1)[-1]
        return None if UNKNOWN in base else base

    def stdin_redirected(self) -> bool:
        if self.stdin_from_pipe:
            return True
        return any(r.op in ("<", "<<", "<<-", "<<<", "<>") and r.fd in ("", "0") for r in self.redirects)


@dataclass
class Parsed:
    commands: list[Simple]
    opaque: list[str]


class _Reader:
    def __init__(self, src: str, depth: int, assigned: set[str], env: dict[str, str]):
        self.s = src
        self.i = 0
        self.depth = depth
        self.assigned = assigned
        self.env = env
        self.raw: list[dict] = []       # raw commands before unwrapping
        self.opaque: list[str] = []
        self.pending_heredocs: list[tuple[dict, str, bool, bool]] = []

    # ---------- low level ----------
    def peek(self, n: int = 1) -> str:
        return self.s[self.i:self.i + n]

    def find_close(self, start: int, open_ch: str = "(", close_ch: str = ")") -> int:
        """Index of the matching close bracket for an opener just before `start`, or -1."""
        depth, i, s = 1, start, self.s
        while i < len(s):
            c = s[i]
            if c == "\\":
                i += 2
                continue
            if c == "'":
                j = s.find("'", i + 1)
                if j == -1:
                    return -1
                i = j + 1
                continue
            if c == '"':
                i += 1
                while i < len(s) and s[i] != '"':
                    i += 2 if s[i] == "\\" else 1
                i += 1
                continue
            if c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        return -1

    def nested(self, text: str, via: str) -> None:
        if self.depth + 1 > MAX_DEPTH:
            self.opaque.append("commands nested too deep to follow")
            return
        sub = parse(text, cwd=None, depth=self.depth + 1, assigned=self.assigned, env=self.env, _raw_only=True)
        for r in sub["raw"]:
            r.setdefault("via", via)
            self.raw.append(r)
        self.opaque.extend(sub["opaque"])

    def expand_var(self, name: str) -> str:
        if name in _KNOWN_VARS and name not in self.assigned and self.env.get(name):
            return self.env[name]
        return UNKNOWN

    # ---------- words ----------
    def read_dollar(self, out: list[str]) -> None:
        s = self.s
        self.i += 1  # past $
        c = self.peek()
        if c == "(":
            if self.peek(2) == "((":
                end = self.s.find("))", self.i + 2)
                self.i = len(s) if end == -1 else end + 2
                out.append(UNKNOWN)
                return
            end = self.find_close(self.i + 1)
            if end == -1:
                self.opaque.append("unbalanced $( )")
                self.i = len(s)
            else:
                self.nested(s[self.i + 1:end], "$()")
                self.i = end + 1
            out.append(UNKNOWN)
        elif c == "{":
            end = self.find_close(self.i + 1, "{", "}")
            if end == -1:
                self.opaque.append("unbalanced ${ }")
                self.i = len(s)
                out.append(UNKNOWN)
                return
            inner = s[self.i + 1:end]
            self.i = end + 1
            out.append(self.expand_var(inner) if re.fullmatch(r"[A-Za-z_]\w*", inner) else UNKNOWN)
        elif c == "'":
            # $'...' ANSI-C quoting: keep the text, drop the quotes
            j = self.i + 1
            buf = []
            while j < len(s) and s[j] != "'":
                if s[j] == "\\" and j + 1 < len(s):
                    buf.append(s[j:j + 2])
                    j += 2
                    continue
                buf.append(s[j])
                j += 1
            self.i = j + 1
            out.append("".join(buf))
        else:
            m = re.match(r"[A-Za-z_]\w*|[0-9@*#?$!-]", s[self.i:])
            if not m:
                out.append("$")
                return
            self.i += m.end()
            out.append(self.expand_var(m.group(0)))

    def read_backtick(self, out: list[str]) -> None:
        s = self.s
        j = self.i + 1
        while j < len(s) and s[j] != "`":
            j += 2 if s[j] == "\\" else 1
        if j >= len(s):
            self.opaque.append("unbalanced backtick")
            self.i = len(s)
        else:
            self.nested(s[self.i + 1:j].replace("\\`", "`"), "$()")
            self.i = j + 1
        out.append(UNKNOWN)

    def read_word(self) -> Word:
        s, out, glob = self.s, [], False
        start = self.i
        while self.i < len(s):
            c = s[self.i]
            if c in " \t\n;&|()<>":
                break
            if c == "\\":
                if self.peek(2) == "\\\n":
                    self.i += 2
                    continue
                out.append(s[self.i + 1:self.i + 2])
                self.i += 2
            elif c == "'":
                j = s.find("'", self.i + 1)
                if j == -1:
                    self.opaque.append("unbalanced single quote")
                    j = len(s)
                out.append(s[self.i + 1:j])
                self.i = j + 1
            elif c == '"':
                self.i += 1
                while self.i < len(s) and s[self.i] != '"':
                    d = s[self.i]
                    if d == "\\" and self.i + 1 < len(s) and s[self.i + 1] in '$`"\\\n':
                        if s[self.i + 1] != "\n":
                            out.append(s[self.i + 1])
                        self.i += 2
                    elif d == "$":
                        self.read_dollar(out)
                    elif d == "`":
                        self.read_backtick(out)
                    else:
                        out.append(d)
                        self.i += 1
                if self.i >= len(s):
                    self.opaque.append("unbalanced double quote")
                self.i += 1
            elif c == "$":
                self.read_dollar(out)
            elif c == "`":
                self.read_backtick(out)
            elif c == "~" and self.i == start and (self.i + 1 >= len(s) or s[self.i + 1] in "/ \t\n;&|)"):
                out.append(self.expand_var("HOME"))
                self.i += 1
            else:
                if c in "*?[":
                    glob = True
                out.append(c)
                self.i += 1
        return Word("".join(out), glob)

    # ---------- commands ----------
    def new_cmd(self, from_pipe: bool) -> dict:
        return {"words": [], "redirects": [], "stdin_from_pipe": from_pipe, "heredoc": None}

    def read_heredoc_bodies(self) -> None:
        for cmd, delim, strip_tabs, expand in self.pending_heredocs:
            lines = []
            while self.i < len(self.s):
                end = self.s.find("\n", self.i)
                line = self.s[self.i:] if end == -1 else self.s[self.i:end]
                self.i = len(self.s) if end == -1 else end + 1
                check = line.lstrip("\t") if strip_tabs else line
                if check == delim:
                    break
                lines.append(line)
            body = "\n".join(lines)
            cmd["heredoc"] = body
            if expand:
                # command substitutions inside an unquoted here-doc run
                sub = _Reader('"' + body.replace('"', '\\"') + '"', self.depth, self.assigned, self.env)
                sub.read_word()
                for r in sub.raw:
                    r.setdefault("via", "$()")
                    self.raw.append(r)
                self.opaque.extend(sub.opaque)
        self.pending_heredocs = []

    def run(self) -> None:
        s = self.s
        cmd = self.new_cmd(False)

        def finish(next_from_pipe: bool) -> dict:
            if cmd["words"] or cmd["redirects"]:
                self.raw.append(cmd)
            return self.new_cmd(next_from_pipe)

        while self.i < len(s):
            c = s[self.i]
            if c in " \t":
                self.i += 1
            elif c == "#" and (self.i == 0 or s[self.i - 1] in " \t\n;&|()"):
                end = s.find("\n", self.i)
                self.i = len(s) if end == -1 else end
            elif c == "\n":
                self.i += 1
                cmd = finish(False)
                if self.pending_heredocs:
                    self.read_heredoc_bodies()
            elif c == "\\" and self.peek(2) == "\\\n":
                self.i += 2
            elif c in ";&|()":
                two = self.peek(2)
                if two in ("&&", "||", ";;"):
                    self.i += 2
                    cmd = finish(False)
                elif two == "|&":
                    self.i += 2
                    cmd = finish(True)
                elif c == "&" and self.peek(2) == "&>":
                    self.read_redirect(cmd, "")
                else:
                    self.i += 1
                    cmd = finish(c == "|")
            elif c in "<>" or (c.isdigit() and re.match(r"\d+[<>]", s[self.i:])):
                fd = ""
                m = re.match(r"\d+", s[self.i:])
                if m:
                    fd = m.group(0)
                    self.i += len(fd)
                self.read_redirect(cmd, fd)
            else:
                cmd["words"].append(self.read_word())
        finish(False)
        if self.pending_heredocs:
            self.read_heredoc_bodies()

    def read_redirect(self, cmd: dict, fd: str) -> None:
        s = self.s
        op = next(o for o in _REDIR_OPS if s.startswith(o, self.i))
        self.i += len(op)
        if op in ("<", ">") and self.peek() == "(":
            end = self.find_close(self.i + 1)
            if end == -1:
                self.opaque.append("unbalanced process substitution")
                self.i = len(s)
            else:
                self.nested(s[self.i + 1:end], "$()")
                self.i = end + 1
            cmd["words"].append(Word(UNKNOWN))
            return
        while self.i < len(s) and s[self.i] in " \t":
            self.i += 1
        if op in ("<<", "<<-"):
            raw_start = self.i
            w = self.read_word()
            quoted = any(q in s[raw_start:self.i] for q in "'\"\\")
            self.pending_heredocs.append((cmd, w.text, op == "<<-", not quoted))
            cmd["redirects"].append(Redirect(op, fd, w))
            return
        target = self.read_word()
        cmd["redirects"].append(Redirect(op, fd, target))


# ---------- unwrapping ----------

def _short_has(word: str, letter: str) -> bool:
    return word.startswith("-") and not word.startswith("--") and letter in word[1:]


def _skip_opts(argv: list[Word], i: int, with_value: set[str], stop_at_first_positional: bool = True) -> int:
    while i < len(argv):
        t = argv[i].text
        if t == "--":
            return i + 1
        if not t.startswith("-") or t == "-":
            return i
        i += 2 if t in with_value else 1
    return i


def _unwrap(raw: dict, reader_env: dict, assigned: set[str], depth: int, cwd: str | None, out: list[Simple],
            opaque: list[str]) -> None:
    words: list[Word] = list(raw["words"])
    assigns: dict[str, Word] = {}
    while words and words[0].text in _KEYWORDS_SKIP:
        words.pop(0)
    if words and words[0].text in _HEADER_KEYWORDS:
        return
    while words and _ASSIGN.match(words[0].text):
        name, _, value = words[0].text.partition("=")
        assigns[name] = Word(value, words[0].glob)
        assigned.add(name)
        words.pop(0)
    via = raw.get("via", "")
    unknown_args = raw.get("unknown_args", False)

    def emit(argv: list[Word], **extra) -> None:
        out.append(Simple(argv=argv, assigns=assigns, redirects=raw["redirects"],
                          stdin_from_pipe=raw["stdin_from_pipe"], heredoc=raw["heredoc"],
                          unknown_args=extra.get("unknown_args", unknown_args),
                          via=extra.get("via", via), cwd=cwd))

    def nested_script(text: str, how: str, more_unknown: bool = False) -> None:
        if depth + 1 > MAX_DEPTH:
            opaque.append("commands nested too deep to follow")
            return
        sub = parse(text, cwd=cwd, depth=depth + 1, assigned=assigned, env=reader_env)
        for c in sub.commands:
            c.via = c.via or how
            c.unknown_args = c.unknown_args or more_unknown
            out.append(c)
        opaque.extend(sub.opaque)

    for _ in range(8):  # peel at most a few wrapper layers
        if not words:
            if raw["words"] == [] and raw["redirects"]:
                return
            return
        w0 = words[0]
        name = w0.text.rsplit("/", 1)[-1] if w0.known else None
        if name in ("command", "builtin", "exec", "nohup", "time", "caffeinate", "chronic"):
            i = _skip_opts(words, 1, set())
            words = words[i:]
            continue
        if name == "nice":
            words = words[_skip_opts(words, 1, {"-n"}):]
            continue
        if name == "stdbuf":
            words = words[_skip_opts(words, 1, {"-i", "-o", "-e"}):]
            continue
        if name in ("sudo", "doas"):
            words = words[_skip_opts(words, 1, {"-u", "-g", "-C", "-h", "-p", "-U", "-r", "-t", "-D"}):]
            continue
        if name == "timeout":
            i = _skip_opts(words, 1, {"-s", "-k", "--signal", "--kill-after"})
            words = words[i + 1:]  # drop the duration
            continue
        if name == "env":
            i = 1
            while i < len(words):
                t = words[i].text
                if t in ("-S", "--split-string") and i + 1 < len(words):
                    if words[i + 1].known:
                        nested_script(words[i + 1].text + " " + " ".join(w.text for w in words[i + 2:]), "env -S")
                    else:
                        opaque.append("env -S with a run-time value")
                    return
                if t in ("-u", "--unset", "-C", "--chdir"):
                    i += 2
                elif t.startswith("-") or _ASSIGN.match(t):
                    if _ASSIGN.match(t):
                        n, _, v = t.partition("=")
                        assigns[n] = Word(v)
                    i += 1
                else:
                    break
            words = words[i:]
            continue
        if name == "xargs":
            i = _skip_opts(words, 1, {"-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a", "--max-args", "--max-procs",
                                      "--delimiter", "--arg-file", "--replace"})
            words = words[i:] or [Word("echo")]
            unknown_args = True
            via = "xargs"
            continue
        if name in _SHELLS:
            i = 1
            script = None
            while i < len(words):
                t = words[i].text
                if t == "-c" or (_short_has(t, "c") and re.fullmatch(r"-[a-zA-Z]+", t)):
                    if i + 1 < len(words):
                        script = words[i + 1]
                    break
                if t in ("-o", "+o", "-O", "+O"):
                    i += 2
                    continue
                if not t.startswith(("-", "+")):
                    break
                i += 1
            if script is not None:
                if script.known:
                    nested_script(script.text, f"{name} -c", unknown_args)
                else:
                    opaque.append(f"{name} -c runs a script known only at run time")
                return
            if i < len(words):
                emit(words)  # runs a script file: the file itself is not read
                return
            if raw["heredoc"] is not None:
                nested_script(raw["heredoc"], f"{name} <<heredoc")
                return
            if raw["stdin_from_pipe"] or any(r.op == "<" for r in raw["redirects"]):
                opaque.append(f"{name} reads a script from stdin")
                return
            emit(words)
            return
        if name == "eval":
            rest = words[1:]
            if all(w.known for w in rest):
                nested_script(" ".join(w.text for w in rest), "eval", unknown_args)
            else:
                opaque.append("eval of a run-time value")
            return
        if name == "find":
            emit(words)
            i = 1
            while i < len(words):
                if words[i].text in ("-exec", "-execdir", "-ok", "-okdir"):
                    j = i + 1
                    while j < len(words) and words[j].text not in (";", "+"):
                        j += 1
                    inner = [Word(UNKNOWN) if w.text == "{}" else w for w in words[i + 1:j]]
                    if inner:
                        sub_raw = {"words": inner, "redirects": [], "stdin_from_pipe": False, "heredoc": None,
                                   "via": "find -exec", "unknown_args": True}
                        _unwrap(sub_raw, reader_env, assigned, depth + 1, cwd, out, opaque)
                    i = j
                i += 1
            return
        break
    emit(words)


def parse(command: str, cwd: str | None = None, depth: int = 0, assigned: set[str] | None = None,
          env: dict[str, str] | None = None, _raw_only: bool = False):
    """Read a command line. Returns Parsed(commands, opaque)."""
    env = dict(os.environ) if env is None else env
    assigned = set() if assigned is None else assigned
    reader = _Reader(command, depth, assigned, env)
    reader.run()
    if _raw_only:
        return {"raw": reader.raw, "opaque": reader.opaque}
    commands: list[Simple] = []
    opaque = list(reader.opaque)
    cur = cwd
    for raw in reader.raw:
        words = raw["words"]
        if words and words[0].known and words[0].text == "cd" and not raw.get("via"):
            target = words[1] if len(words) > 1 else Word(env.get("HOME", UNKNOWN))
            if cur is not None and target.known and not target.glob and target.text != "-":
                cur = os.path.normpath(os.path.join(cur, os.path.expanduser(target.text)))
            else:
                cur = None
            continue
        if words and words[0].known and words[0].text in ("export", "declare", "local", "readonly", "typeset"):
            for w in words[1:]:
                if _ASSIGN.match(w.text):
                    assigned.add(w.text.split("=", 1)[0])
            continue
        _unwrap(raw, env, assigned, depth, cur, commands, opaque)
    return Parsed(commands, opaque)
