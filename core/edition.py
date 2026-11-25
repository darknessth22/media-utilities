"""Which edition is running.

Official builds include the private ``videl_pro`` package (the Pro tools).
The public repo builds without it: same app, free tools only.
"""
from importlib.util import find_spec

HAS_PRO = find_spec("videl_pro") is not None
