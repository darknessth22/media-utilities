"""Which edition is running.

Official builds include the private ``videl_pro`` package (the Pro tools).
The public repo builds without it: same app, free tools only.
"""
from importlib.util import find_spec

HAS_PRO = find_spec("videl_pro") is not None


def pro_gate(tool: str, **kw) -> None:
    """A Pro check inside a free tool: a batch, 16-bit TIFF, a large background model.

    Raises videl_pro.quota.ProRequired when the free allowance does not cover it,
    and counts one free run when it does. A build without videl_pro has no gate.
    tool and kw are videl_pro.quota.start_job's.
    """
    if HAS_PRO:
        from videl_pro import quota

        quota.start_job(tool, **kw)


def pro_mark(label: str) -> str:
    """An option's label with "(Pro)" added in builds that sell Pro."""
    return f"{label} (Pro)" if HAS_PRO else label
