"""`python -m app.modules.newsfeed migrate`: back the database up, then convert the Business, Social and Search rows into the feed."""

import sys

from app.config import load
from app.modules.newsfeed.migrate import main

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.exit(main(sys.argv[1:], load()))
