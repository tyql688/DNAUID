def get_main_url():
    return "https://dnabbs-api.yingxiong.com"


MAIN_URL = get_main_url()
LOGIN_URL = f"{MAIN_URL}/user/sdkLogin"
GET_RSA_PUBLIC_KEY_URL = f"{MAIN_URL}/config/getRsaPublicKey"
LOGIN_LOG_URL = f"{MAIN_URL}/user/login/log"
ROLE_LIST_URL = f"{MAIN_URL}/role/list"


BBS_SIGN_URL = f"{MAIN_URL}/user/signIn"
HAVE_SIGN_IN_URL = f"{MAIN_URL}/user/haveSignInNew"
SIGN_CALENDAR_URL = f"{MAIN_URL}/encourage/signin/show"
GAME_SIGN_URL = f"{MAIN_URL}/encourage/signin/signin"
