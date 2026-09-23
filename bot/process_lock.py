"""One delivery process per data directory on supported macOS/Linux hosts."""
import fcntl


class ProcessLock:
    def __init__(self, path):
        self.file = path.open("a")
        try:
            fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            self.file = None
            raise RuntimeError("Another bot process is using this data directory") from None

    def close(self):
        if self.file is not None:
            self.file.close()  # Closing releases flock; never unlink the shared lock-file inode.
            self.file = None
