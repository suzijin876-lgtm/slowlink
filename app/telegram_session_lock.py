import threading

# Telethon .session is SQLite. Only one standalone client should touch it at a time.
# When the listener is running, tests must reuse the listener client instead.
SESSION_LOCK = threading.RLock()
