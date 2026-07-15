import logging

log = logging.getLogger("agnetic-governance")


class GovernanceManager:
    def __init__(self, config=None):
        self.config = config or {}
        self.policies = []
        log.info("GovernanceManager initialized")

    async def check_action(self, agent_name, action, context=None):
        return {"approved": True, "reason": "no policy restrictions"}

    def get_status(self):
        return {"enabled": True, "policies": len(self.policies), "mode": "permissive"}
