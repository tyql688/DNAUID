from typing import Dict

from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsIntConfig,
    GsStrConfig,
    GsBoolConfig,
    GsDictConfig,
    GsListConfig,
    GsListStrConfig,
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
    "AnnMinuteCheck": GsIntConfig("公告推送时间检测（单位min）", "公告推送时间检测（单位min）", 10, 60),
    "DNALoginUrl": GsStrConfig(
        "二重螺旋登录url",
        "local 模式：登录页对外域名，留空则用 Core 的 HOST/PORT 并自动探测公网 IP；外置模式：必填 dna-login 服务的 base URL",
        "",
    ),
    "DNALoginTransport": GsStrConfig(
        "登录接入方式",
        "local = Core 进程内嵌登录；http_poll / sse / ws = 走外置 dna-login 服务（EdgeOne 部署只支持 http_poll）",
        "local",
        options=["local", "http_poll", "sse", "ws"],
    ),
    "DNALoginSecret": GsStrConfig(
        "外置登录共享密钥",
        "外置模式下与 dna-login 服务的 SHARED_SECRET 一致；HMAC 校验，留空则不签名",
        "",
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
    "MaxBindNum": GsIntConfig("绑定UID限制数量（未登录）", "绑定UID限制数量（未登录）", 2, 100),
    "MHSubscribe": GsListStrConfig(
        "密函订阅开关",
        "private=私聊;group=群聊",
        data=["group"],
        options=["private", "group"],
    ),
    "MHPushSubscribe": GsStrConfig(
        "密函推送时间设置",
        "每小时推送一次密函【分钟:秒】，重启生效",
        "00:30",
    ),
    "MHCache": GsBoolConfig(
        "是否进行密函缓存",
        "每整点缓存一次，缓存后将不再请求API，直接读取缓存数据",
        True,
    ),
    "Guide": GsListStrConfig(
        "角色攻略图提供方",
        "使用DNA角色攻略时选择的提供方",
        ["all"],
        options=["all", "狩月庭攻略组", "猫冬"],
    ),
    "DNAUrlProxyUrl": GsStrConfig(
        "二重螺旋API代理地址",
        "二重螺旋API代理地址",
        "",
    ),
    "LocalProxyUrl": GsStrConfig(
        "本地代理地址",
        "本地代理地址",
        "",
    ),
    "NeedProxyFunc": GsListStrConfig(
        "需要代理的函数",
        "需要代理的函数",
        [],
        options=["all", "get_sms_code", "login"],
    ),
    "NoNeedProxyFunc": GsListStrConfig(
        "不需要代理的函数",
        "这个优先级会更高",
        [],
        options=[],
    ),
    "WebSocketContinueTime": GsIntConfig(
        "WebSocket持续时间",
        "保证每小时都活跃的话，可以设置>3600秒, 更改后立即生效",
        300,
        86400,
    ),
    "WebSocketWaitTime": GsIntConfig(
        "WebSocket等待时间",
        "等待WebSocket连接建立完成的时间(秒)",
        5,
        30,
    ),
    "RoleInfoCard": GsBoolConfig(
        "角色信息卡片是否显示未拥有的角色和武器",
        "开启就显示全部，关闭只显示已拥有的角色和武器",
        True,
    ),
    "RoleOriginalImage": GsBoolConfig(
        "角色原图功能开关",
        "开启后，可以引用角色面板图获取上传原图",
        True,
    ),
    "MHSimplePicture": GsBoolConfig(
        "是否使用简单密函图片",
        "是否使用简单密函图片",
        False,
    ),
    "AllowAtQuery": GsBoolConfig(
        "允许AT查询他人信息",
        "开启后，可以通过@他人查询对方的角色面板等信息；关闭时，无论是否AT都只能查看自己的信息",
        True,
    ),
}
