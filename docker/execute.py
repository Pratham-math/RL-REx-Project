"""Trusted runner wrapper. Executed inside the container; never imported by the host.

Compile mode does not execute source. Run mode replaces this process, so Docker's
exec lifecycle ExitCode belongs to the program, not candidate-provided metadata.
"""
import base64
import os
import resource
import sys

resource.setrlimit(resource.RLIMIT_CPU, (int(sys.argv[2]), int(sys.argv[2]) + 1))
resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
if sys.argv[1] == "compile":
    try:
        with open("/candidate/main.py", "rb") as stream:
            compile(stream.read(), "/candidate/main.py", "exec")
    except (SyntaxError, ValueError, OverflowError) as exc:
        print(str(exc)[:2000], file=sys.stderr)
        sys.exit(42)
else:
    # Input is supplied by the host as bytes, never evaluated. Expected output stays on host.
    data = base64.b64decode(sys.argv[3], validate=True)
    fd = os.open("/tmp/input", os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(fd, data)
    os.lseek(fd, 0, os.SEEK_SET)
    os.dup2(fd, 0)
    os.close(fd)
    os.execv(sys.executable, [sys.executable, "-I", "-B", "/candidate/main.py"])
