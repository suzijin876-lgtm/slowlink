import faulthandler
import logging
import os
import signal


faulthandler.enable()
STACK_DUMP_PATH = os.getenv("STACK_DUMP_PATH", "/tmp/slowlink_python_stack.log")
_stack_dump_file = None
try:
    _stack_dump_file = open(STACK_DUMP_PATH, "a", encoding="utf-8", buffering=1)
    faulthandler.register(signal.SIGUSR1, file=_stack_dump_file, all_threads=True, chain=False)
except (AttributeError, OSError, RuntimeError, ValueError):
    if _stack_dump_file is not None:
        _stack_dump_file.close()
    pass

logging.getLogger("telethon").setLevel(logging.ERROR)

from waitress import serve
from config import WEB_HOST, WEB_PORT, WEB_THREADS
from web import app

if __name__ == "__main__":
    serve(app, host=WEB_HOST, port=WEB_PORT, threads=WEB_THREADS)
