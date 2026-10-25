"""One bounded startup stack dump if the real API never reports healthy.

CPython's watchdog runs independently of the Python event loop. It emits
thread stacks, not locals, credentials, request bodies or calendar contents.
No health deadline, exit code, service state or update decision is changed.
"""
import faulthandler
import logging
import sys

log=logging.getLogger(__name__)
_armed=False


def arm():
    global _armed
    if _armed:
        return
    try:
        faulthandler.dump_traceback_later(30,repeat=False,file=sys.stderr,exit=False)
        _armed=True
    except (OSError,RuntimeError,ValueError):
        log.warning('Startup stack diagnostic unavailable; health verification remains required')


def healthy():
    global _armed
    if _armed:
        faulthandler.cancel_dump_traceback_later()
        _armed=False
