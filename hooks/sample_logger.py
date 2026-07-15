import logging

log = logging.getLogger("sample-hook")


def register_hooks(hook_manager):
    hook_manager.register("agent.startup", on_startup, name="sample_logger", priority=10)
    hook_manager.register("agent.shutdown", on_shutdown, name="sample_logger", priority=10)
    hook_manager.register("tool.after_execution", on_tool_complete, name="sample_logger", priority=5)
    log.info("Sample logger hooks registered")


def on_startup(event, context):
    agent = context.get("agent", "unknown")
    log.info("[HOOK] Agent startup: %s", agent)
    return {"logged": True, "agent": agent}


def on_shutdown(event, context):
    agent = context.get("agent", "unknown")
    log.info("[HOOK] Agent shutdown: %s", agent)
    return {"logged": True, "agent": agent}


def on_tool_complete(event, context):
    tool = context.get("tool", "unknown")
    result = context.get("result", {})
    log.info("[HOOK] Tool completed: %s (error=%s)", tool, result.get("error", "?"))
    return {"logged": True, "tool": tool}
