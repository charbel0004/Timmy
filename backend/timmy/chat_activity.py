"""Operational events only: never include prompts, model output, or document data."""
import json
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from time import monotonic


class ChatActivity:
    def __init__(self):
        self.traces = OrderedDict()
        self.logger = logging.Logger("timmy.chat_activity")
        try:
            path = Path(__file__).resolve().parents[2] / "logs" / "assistant.log"
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.logger.addHandler(RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3,
                                                       encoding="utf-8"))
        except OSError:
            logging.getLogger(__name__).warning("Could not initialize local assistant log")

    def start(self, key):
        steps = []
        started = monotonic()
        self.traces[key] = steps
        self.traces.move_to_end(key)
        while len(self.traces) > 256:
            self.traces.popitem(last=False)

        def record(step, **details):
            steps.append(step)
            try:
                self.logger.info(json.dumps({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "request_id": key[1], "step": step,
                    "elapsed_ms": round((monotonic() - started) * 1000), **details,
                }))
            except OSError:
                logging.getLogger(__name__).warning("Could not write local assistant log")
        return steps, record
