from gsuid_core.utils.plugins_config.gs_config import StringConfig

from ..utils.resource.RESOURCE_PATH import CONFIG_PATH, SIGN_CONFIG_PATH
from .config_default import CONFIG_DEFAULT
from .config_sign import CONFIG_SIGN

DNAConfig = StringConfig(
    "DNAUID",
    CONFIG_PATH,
    CONFIG_DEFAULT,
)

DNASignConfig = StringConfig(
    "DNAUID签到配置",
    SIGN_CONFIG_PATH,
    CONFIG_SIGN,
)
