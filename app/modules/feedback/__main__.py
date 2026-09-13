"""`python -m app.modules.feedback list|clear <module>...`: the queue the repo's workflows read before work and drain after it."""

import sys

from app.config import load
from app.modules.feedback.queue import main

sys.exit(main(sys.argv[1:], load()))
