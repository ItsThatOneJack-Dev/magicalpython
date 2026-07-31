# MagicalPython

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://itoj.dev/embed/Wwatermark.png">
  <source media="(prefers-color-scheme: light)" srcset="https://itoj.dev/embed/Bwatermark.png">
  <img alt="ItsThatOneJack, Copyright, All Rights Reserved Unless Stated Otherwise. Follow the license!" src="https://itoj.dev/embed/Bwatermark.png">
</picture>

<p align="center"><strong>MagicalPython</strong> <em>&mdash; I originally wanted to call it Python++ :c</em></p>

---

![License](https://img.shields.io/badge/License%20-%20ZPL%201.0%20-%20%23007EC6?style=for-the-badge)
![License](https://img.shields.io/badge/Python%20-%20CPython%20%3E%3D3.8%20-%20%23007EC6?style=for-the-badge)

---

**why?**
`/waɪ/` • *adverb*

> **Definition** > For what reason, cause, or purpose; to what end. Used to question the motivation, justification, or necessity behind an action.

**E.g.:** `"Why would you ever make that?"`

I know what you are thinking: "Why would someone ever make this?" Well, the answer is "because I can." There are so many cautionary tales about the dangers of thinking about "why not" rather than "why" that nobody ever stops to actually think "I can make that, why shouldn't I?" I strive to change that.

*That* is why I made this monstrosity. Python with nearly everything nobody ever thought "why not!" about.

## Features

- `Result` type (you have to use it, literally every function will always return one).
- Lazy errors (they don't raise immediately, but they can if you want them to).
- Rust's `?` operator, except its a function called `q`.
- Fancy tracebacks.
- A fancy segfault message, for you Windows users out there.
- Inline assembly.
  - Clobbers.
  - Automatic ctype resolution.
  - Introspection.
  - Per-architecture and per-OS assembly.
- Memory stuff!
  - Malloc & calloc.
  - Automatic local/remote mode.
  - Memory protection.
  - C-style bitfields.
  - Unions.
  - Memory scanning, because we feel like a cheat written in this would be hilarious.
    - AoB (Array of Bytes) scanning.
- Semi-automatic privilege escalation (via UAC on Windows or cached sudo creds on Linux/MacOS).
- CPU feature detection.
  - Raw CPUID leaves, in case you want them.
- GCC-style `__builtins__`.
- Crash handler registration.
- Exit handler registration.
- Atomics (technically not atomic, but the only access to the memory you need an atomic for is within an atomic CPU instruction), so it counts.
  - Spinlocks.
