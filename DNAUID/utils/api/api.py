def get_main_url():
    return "https://dnabbs-api.yingxiong.com"


MAIN_URL = get_main_url()
LOGIN_URL = f"{MAIN_URL}/user/sdkLogin"
GET_RSA_PUBLIC_KEY_URL = f"{MAIN_URL}/config/getRsaPublicKey"
LOGIN_LOG_URL = f"{MAIN_URL}/user/login/log"
ROLE_LIST_URL = f"{MAIN_URL}/role/list"


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
