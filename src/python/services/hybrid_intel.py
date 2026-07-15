import logging

log = logging.getLogger("agnetic-intel")


class IntelItem:
    def to_dict(self):
        return {}


class HybridIntel:
    def __init__(self):
        self.latest_items = []
        self.latest_signals = []
        self.sources = []
        self.status = {}
        self._sweep_running = False
        log.info("HybridIntel initialized (stub)")

    def get_status(self):
        return {"enabled": False, "items": 0, "sweeping": self._sweep_running}

    async def sweep(self):
        pass

    async def generate_brief(self):
        return {"summary": "Intel engine not fully configured", "items": []}

    def get_deltas(self, minutes=60):
        return []
