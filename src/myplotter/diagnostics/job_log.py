import json
import logging
import queue
import re
from datetime import datetime
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path


class JobLog:
    def __init__(self, source, kind, directory=None):
        folder = Path(directory) if directory is not None else Path(__file__).resolve().parents[3] / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(source).stem).strip(" .") or "manual"
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S_%f")
        self.path = folder / f"{stem}_{stamp}_{kind}.log"
        self.handler = logging.FileHandler(self.path, mode="x", encoding="utf-8")
        self.handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self.records = queue.SimpleQueue()
        self.listener = QueueListener(self.records, self.handler)
        self.logger = logging.Logger(f"myplotter.job.{stamp}", level=logging.INFO)
        self.logger.addHandler(QueueHandler(self.records))
        self.closed = False
        self.listener.start()

    def event(self, name, **fields):
        if not self.closed:
            self.logger.info("%s %s", name, json.dumps(fields, ensure_ascii=False, default=str))

    def close(self):
        if not self.closed:
            self.closed = True
            self.listener.stop()
            self.handler.close()
