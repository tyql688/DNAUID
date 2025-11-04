def get_main_url():
    return "https://dnabbs-api.yingxiong.com"


MAIN_URL = get_main_url()
LOGIN_URL = f"{MAIN_URL}/user/sdkLogin"
GET_RSA_PUBLIC_KEY_URL = f"{MAIN_URL}/config/getRsaPublicKey"

ROLE_LIST_URL = f"{MAIN_URL}/role/list"
