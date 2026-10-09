def get_main_url():
    from ...dna_config.dna_config import DNAConfig

    DNAUrlProxyUrl = DNAConfig.get_config("DNAUrlProxyUrl").data
    return DNAUrlProxyUrl or "https://dnabbs-api.yingxiong.com"


MAIN_URL = get_main_url()
LOGIN_URL = f"{MAIN_URL}/user/sdkLogin"
GET_RSA_PUBLIC_KEY_URL = f"{MAIN_URL}/config/getRsaPublicKey"
GET_SMS_CODE_URL = f"{MAIN_URL}/user/getSmsCode"
LOGIN_LOG_URL = f"{MAIN_URL}/user/login/log"
ROLE_LIST_URL = f"{MAIN_URL}/role/list"
ROLE_FOR_TOOL_URL = f"{MAIN_URL}/role/defaultRoleForTool"
# role detail
ROLE_DETAIL_URL = f"{MAIN_URL}/role/getCharDetail"
# weapon detail
WEAPON_DETAIL_URL = f"{MAIN_URL}/role/getWeaponDetail"
# refresh token
REFRESH_TOKEN_URL = f"{MAIN_URL}/user/refreshToken"

# mr
SHORT_NOTE_URL = f"{MAIN_URL}/role/getShortNoteInfo"

# 周报
ITEM_WEEKLY_REPORT_URL = f"{MAIN_URL}/role/getItemWeeklyReport"


# game sign
SIGN_CALENDAR_URL = f"{MAIN_URL}/encourage/signin/show"
GAME_SIGN_URL = f"{MAIN_URL}/encourage/signin/signin"
# bbs sign
BBS_SIGN_URL = f"{MAIN_URL}/user/signIn"
HAVE_SIGN_IN_URL = f"{MAIN_URL}/user/haveSignInNew"

GET_TASK_PROCESS_URL = f"{MAIN_URL}/encourage/level/getTaskProcess"
GET_POST_LIST_URL = f"{MAIN_URL}/forum/list"
GET_POST_DETAIL_URL = f"{MAIN_URL}/forum/getPostDetail"
LIKE_POST_URL = f"{MAIN_URL}/forum/like"
SHARE_POST_URL = f"{MAIN_URL}/encourage/level/shareTask"
REPLY_POST_URL = f"{MAIN_URL}/forum/comment/createComment"


# ann
ANN_LIST_URL = f"{MAIN_URL}/user/mine"


# calendar
CALENDAR_LIST_URL = f"{MAIN_URL}/forum/wiki/home/page/list"
ACTIVITY_LIST_URL = f"{MAIN_URL}/encourage/calendar/Activity/list"

# wiki
WIKI_HOME_LIST_URL = f"{MAIN_URL}/forum/wiki/home/page/list"
WIKI_LIST_URL = f"{MAIN_URL}/forum/wiki/list"
WIKI_DETAIL_URL = f"{MAIN_URL}/forum/wiki/getDetail"


def get_local_proxy_url():
    from ...dna_config.dna_config import DNAConfig

    LocalProxyUrl = DNAConfig.get_config("LocalProxyUrl").data
    if LocalProxyUrl:
        return LocalProxyUrl
    return None


def get_need_proxy_func():
    from ...dna_config.dna_config import DNAConfig

    NeedProxyFunc = DNAConfig.get_config("NeedProxyFunc").data
    if NeedProxyFunc:
        return NeedProxyFunc
    return []


def get_no_need_proxy_func():
    from ...dna_config.dna_config import DNAConfig

    NoNeedProxyFunc = DNAConfig.get_config("NoNeedProxyFunc").data
    if NoNeedProxyFunc:
        return NoNeedProxyFunc
    return []
