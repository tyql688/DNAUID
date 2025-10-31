from gsuid_core.utils.plugins_config.gs_config import StringConfig

from ..utils.resource.RESOURCE_PATH import CONFIG_PATH
from .config_default import CONFIG_DEFAULT

DNAConfig = StringConfig(
    "DNAUID",
    CONFIG_PATH,
    CONFIG_DEFAULT,
)
