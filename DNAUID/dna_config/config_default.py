from typing import Dict

from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsBoolConfig,
    GsDictConfig,
    GsIntConfig,
    GsListConfig,
    GsStrConfig,
)

CONFIG_DEFAULT: Dict[str, GSC] = {
    "DNAAnnGroups": GsDictConfig(
        "推送公告群组",
        "二重螺旋公告推送群组",
        {},
    ),
    "DNAAnnIds": GsListConfig(
        "推送公告ID",
        "二重螺旋公告推送ID列表",
        [],
    ),
    "DNAAnnOpen": GsBoolConfig(
        "公告推送总开关",
        "二重螺旋公告推送总开关",
        True,
    ),
    "AnnMinuteCheck": GsIntConfig(
        "公告推送时间检测（单位min）", "公告推送时间检测（单位min）", 10, 60
    ),
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
    "MaxBindNum": GsIntConfig(
        "绑定UID限制数量（未登录）", "绑定UID限制数量（未登录）", 2, 100
    ),
}
