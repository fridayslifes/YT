"""Master/worker orchestration for the FrameForge production pipeline.

The master plans a task DAG, dispatches typed workers, independently verifies
each result, records a durable ledger, and blocks release on critical failures.
"""

__version__ = "1.0.0"
__all__ = ["contracts", "master", "state", "tools", "verifiers", "workers", "workflows"]
