# MagicalPython

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://itoj.dev/embed/Wwatermark.png">
  <source media="(prefers-color-scheme: light)" srcset="https://itoj.dev/embed/Bwatermark.png">
  <img alt="ItsThatOneJack, Copyright, All Rights Reserved Unless Stated Otherwise. Follow the license!" src="https://itoj.dev/embed/Bwatermark.png">
</picture>

## C Build Commands

Simply `cd` into the project root and run the Windows and then Linux/MacOS build commands, assuming you are on Windows.

### Windows

```nushell
gcc -shared -O2 -o src/native/segfault_msg.dll src/native/segfault_msg.c
```

### Linux/MacOS

```nushell
docker run --rm -v $"($env.PWD):/work" -w /work gcc:latest gcc -shared -fPIC -O2 -o src/native/segfault_msg.so src/native/segfault_msg.c
```
