from typing import Dict

from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsBoolConfig,
    GsStrConfig,
)

CONFIG_DEFAULT: Dict[str, GSC] = {
    "DNALoginUrl": GsStrConfig(
        "二重螺旋登录url",
        "用于设置DNAUID登录界面的配置",
        "",
    ),
    "DNALoginUrlSelf": GsBoolConfig(
        "强制【二重螺旋登录url】为自己的域名",
        "强制【二重螺旋登录url】为自己的域名",
        False,
    ),
    "DNATencentWord": GsBoolConfig(
        "腾讯文档",
        "腾讯文档",
        False,
    ),
    "DNAQRLogin": GsBoolConfig(
        "开启后，登录链接变成二维码",
        "开启后，登录链接变成二维码",
        False,
    ),
    "DNALoginForward": GsBoolConfig(
        "开启后，登录链接变为转发消息",
        "开启后，登录链接变为转发消息",
        False,
    ),
}
