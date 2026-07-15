#!/usr/bin/env python3
"""Starship OS Workflow Engine — standalone daemon that processes workflow requests."""

import sys
import os
import json
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("workflow-engine")

NATS_URL = os.getenv("NATS_URL", "nats://127.0.0.1:4222")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from workflows import WORKFLOWS, handle_workflow_request


async def main():
    from nats import connect as nats_connect

    nc = await nats_connect(NATS_URL)
    log.info("Workflow Engine connected to NATS: %s", NATS_URL)
    log.info("Registered workflows: %s", ", ".join(WORKFLOWS.keys()))

    await nc.subscribe("agnetic.workflow.>", cb=handle_workflow_request)
    log.info("Listening on agnetic.workflow.>")

    # Keep alive
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
