from sys import stdout, stderr
from os import devnull

class SuppressOutput:
    def __enter__(self):
        self._original_stdout = stdout
        self._original_stderr = stderr
        stdout = open(devnull, 'w')
        stderr = open(devnull, 'w')

    def __exit__(self):
        stdout.close()
        stderr.close()
        stdout = self._original_stdout
        stderr = self._original_stderr