# Building

MagicalPython is composed of a mix of mostly Python code, as well as a bit of C code used in the segfault handler.

For this reason, the C code must be built into a DLL (for Windows) and an SO (for Linux/MacOS).
I recommend this is done from a Windows device that possesses an install of Docker.
The commands here will be listed for Nushell.

## Building for Windows

```nushell
gcc -shared -O2 -o src/magicalpython/native/segfault_msg.dll src/magicalpython/native/segfault_msg.c
```

## Building for Linux and MacOS

```nushell
docker run --rm -v $"($env.PWD):/work" -w /work gcc:latest gcc -shared -fPIC -O2 -o src/magicalpython/native/segfault_msg.so src/magicalpython/native/segfault_msg.c
```
