# Third-party software notices

This application invokes independently maintained media tools. It does not claim authorship of their extraction, media-processing, or JavaScript engines.

## yt-dlp

- Project / corresponding source: https://github.com/yt-dlp/yt-dlp
- Initially verified release: https://github.com/yt-dlp/yt-dlp/releases/tag/2026.08.19
- Core source license: Unlicense.
- The official Windows executable contains additional components. Their complete upstream notice is preserved in the adjacent `licenses` directory, including applicable GPL and other licenses. The Windows release executable's combined license differs from the core source license; consult the official README licensing section.
- Updating replaces this external executable with the latest official stable release. Review that release's notices before redistributing.

## Python / Tcl / Tk / PyInstaller

- Python: https://www.python.org/ — Python Software Foundation License (and bundled component notices).
- Tcl / Tk: https://www.tcl.tk/ — Tcl/Tk license.
- PyInstaller: https://pyinstaller.org/ — GPL with the documented bootloader exception permitting distribution of bundled applications under their own license.
- License notices from the actual local Python/Tk/PyInstaller installation are copied into `licenses` during this project's initial build preparation. Source projects: https://github.com/python/cpython , https://github.com/tcltk/tcl , https://github.com/tcltk/tk , https://github.com/pyinstaller/pyinstaller .

## External tools not included in the default build

- FFmpeg / FFprobe: https://ffmpeg.org/ ; source https://git.ffmpeg.org/ffmpeg.git . License depends on build options. This machine uses Gyan FFmpeg 8.1 full build with `--enable-gpl`; see https://www.gyan.dev/ffmpeg/builds/ and https://ffmpeg.org/legal.html .
- Node.js: https://nodejs.org/ ; source and complete license https://github.com/nodejs/node . MIT plus bundled third-party notices.

The default packaged application relies on these tools already installed on the destination computer. The optional build switch that copies these binaries is provided for local use, not as a claim that redistribution obligations are satisfied. A public portable distribution must include all required notices and corresponding source / valid source offers as applicable.

## Public download test asset

Big Buck Bunny trailer: https://download.blender.org/peach/trailer/trailer_400p.ogg

(c) copyright 2008, Blender Foundation / www.bigbuckbunny.org

Creative Commons Attribution 3.0: https://creativecommons.org/licenses/by/3.0/ . Official attribution / license: https://peach.blender.org/about/ . Used only to test a public HTTPS download; test media is not included in the application distribution.