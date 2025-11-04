from typing import Dict

from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsBoolConfig,
    GsIntConfig,
    GsListStrConfig,
    GsTimeConfig,
)

CONFIG_SIGN: Dict[str, GSC] = {
    "DNASignin": GsBoolConfig(
        "二重螺旋游戏签到开关",
        "二重螺旋游戏签到开关",
        False,
    ),
    "DNABBSSignin": GsBoolConfig(
        "皎皎角社区任务开关",
        "皎皎角社区任务开关",
        False,
    ),
    "DNABBSLink": GsListStrConfig(
        "皎皎角社区任务列表",
        "皎皎角社区任务列表",
        ["bbs_sign", "bbs_detail", "bbs_like", "bbs_share", "bbs_reply"],
        options=[
            "bbs_sign",
            "bbs_detail",
            "bbs_like",
            "bbs_share",
            "bbs_reply",
        ],
    ),
    "SigninMaster": GsBoolConfig(
        "全部开启签到",
        "开启后自动帮登录的人签到",
        False,
    ),
    "SchedSignin": GsBoolConfig(
        "定时游戏签到开关",
        "定时游戏签到开关",
        False,
    ),
    "BBSSchedSignin": GsBoolConfig(
        "定时皎皎角社区任务开关",
        "定时皎皎角社区任务开关",
        False,
    ),
    "SignTime": GsTimeConfig(
        "每晚签到时间设置",
        "每晚二重螺旋签到时间设置",
        "00:05",
    ),
    "SigninConcurrentNum": GsIntConfig(
        "自动签到并发数量", "自动签到并发数量", 1, max_value=50
    ),
    "SigninConcurrentNumInterval": GsListStrConfig(
        "自动签到并发数量间隔，默认3-5秒",
        "自动签到并发数量间隔，默认3-5秒",
        ["3", "5"],
    ),
    "PrivateSignReport": GsBoolConfig(
        "签到私聊报告",
        "关闭后将不再给任何人推送当天签到任务完成情况",
        False,
    ),
    "GroupSignReport": GsBoolConfig(
        "签到群组报告",
        "关闭后将不再给任何群推送当天签到任务完成情况",
        False,
    ),
    "GroupSignReportPic": GsBoolConfig(
        "签到群组图片报告",
        "签到以图片形式报告",
        False,
    ),
}
