from gsuid_core.sv import get_plugin_available_prefix


def dna_prefix() -> str:
    return get_plugin_available_prefix("DNAUID")
