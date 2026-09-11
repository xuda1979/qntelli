"""qntelli model hardware standard — ion-trap device access layer.

Public API:
    from hardware import get_device, list_devices, submit_job, JobRecord,
    IonTrapDevice, ExecutionTier, GateFamily, QpuAdapter

The device catalog is built from ``list_devices()``/``get_device()``; there is
no separate ``DeviceRegistry`` class (that export name was stale and caused
``import hardware`` to raise ImportError).
"""
from .standard import (  # noqa: F401
    ExecutionTier,
    GateFamily,
    IonTrapDevice,
    JobRecord,
    QpuAdapter,
    get_device,
    list_devices,
    submit_job,
)
