import logging
logging.getLogger("telethon").setLevel(logging.ERROR)

from waitress import serve
from config import WEB_HOST, WEB_PORT, WEB_THREADS
from web import app

if __name__ == "__main__":
    serve(app, host=WEB_HOST, port=WEB_PORT, threads=WEB_THREADS)
