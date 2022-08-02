import shutil
import os
import contextlib
import subprocess


def tool_exists(tool):
    return subprocess.run(["which", tool]).returncode == 0


@contextlib.contextmanager
def remove_files(paths):

    # change names
    for i in paths:
        with contextlib.suppress(FileNotFoundError):
            shutil.move(i, f"{i}.bak")
    yield

    # restore the names
    for i in paths:
        with contextlib.suppress(FileNotFoundError):
            shutil.move(f"{i}.bak", i)
