#!/usr/bin/env python3
"""System Telemetry Collector — publishes CPU/memory/disk/net to NATS."""

import asyncio
import json
import os
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("system-telemetry")

NATS_URL = os.getenv("NATS_URL", "nats://127.0.0.1:4222")
INTERVAL = int(os.getenv("TELEMETRY_INTERVAL", "15"))


def get_cpu():
    with open("/proc/stat") as f:
        line = f.readline()
    parts = line.strip().split()
    if len(parts) >= 5:
        user, nice, system, idle = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
        total = user + nice + system + idle
        return {"user": user, "system": system, "idle": idle, "total": total}
    return {"user": 0, "system": 0, "idle": 0, "total": 0}


def get_memory():
    mem = {}
    with open("/proc/meminfo") as f:
        for line in f:
            parts = line.split()
            if parts[0].startswith("MemTotal"):
                mem["total"] = int(parts[1]) * 1024
            elif parts[0].startswith("MemAvailable"):
                mem["available"] = int(parts[1]) * 1024
            elif parts[0].startswith("MemFree"):
                mem["free"] = int(parts[1]) * 1024
    if "total" in mem and "available" in mem:
        mem["used"] = mem["total"] - mem["available"]
        mem["percent"] = round(mem["used"] / mem["total"] * 100, 1)
    return mem


def get_disk():
    stat = os.statvfs("/")
    total = stat.f_frsize * stat.f_blocks
    free = stat.f_bfree * stat.f_frsize
    used = total - free
    return {"total": total, "used": used, "free": free, "percent": round(used / total * 100, 1)}


def get_net():
    rx, tx = 0, 0
    with open("/proc/net/dev") as f:
        for line in f:
            if ":" in line:
                parts = line.strip().split()
                rx += int(parts[1])
                tx += int(parts[9])
    return {"rx_bytes": rx, "tx_bytes": tx}


def get_load():
    with open("/proc/loadavg") as f:
        parts = f.read().strip().split()
    return {"1min": float(parts[0]), "5min": float(parts[1]), "15min": float(parts[2])}


async def publish_telemetry(nc):
    cpu = get_cpu()
    mem = get_memory()
    disk = get_disk()
    net = get_net()
    load = get_load()

    full = {
        "cpu": cpu,
        "memory_used": mem.get("used", 0),
        "memory_total": mem.get("total", 0),
        "memory_percent": mem.get("percent", 0),
        "disk_used": disk.get("used", 0),
        "disk_total": disk.get("total", 0),
        "disk_percent": disk.get("percent", 0),
        "rx_bytes": net.get("rx_bytes", 0),
        "tx_bytes": net.get("tx_bytes", 0),
        "load": load,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }

    await nc.publish("agnetic.telemetry", json.dumps(full).encode())
    await nc.publish("agnetic.telemetry.cpu", json.dumps(cpu).encode())
    await nc.publish("agnetic.telemetry.mem", json.dumps(mem).encode())
    log.info("Published system telemetry (CPU=%s%%, Mem=%s%%, Disk=%s%%)",
             cpu.get("percent", "?"), mem.get("percent", "?"), disk.get("percent", "?"))


async def main():
    from nats import connect as nats_connect
    nc = await nats_connect(NATS_URL)
    log.info("Connected to NATS: %s", NATS_URL)

    while True:
        try:
            await publish_telemetry(nc)
        except Exception as e:
            log.warning("Telemetry publish error: %s", e)
        await asyncio.sleep(INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
