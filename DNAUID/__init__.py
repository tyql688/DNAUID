"""init"""

from gsuid_core.sv import Plugins

Plugins(
    name="DNAUID",
    force_prefix=["dna", "DNA", "jjj", "JJJ"],
    allow_empty_prefix=False,
)
