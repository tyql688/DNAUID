class BBSMarkName(str):
    BBS_SIGN = "bbs_sign"
    BBS_DETAIL = "bbs_detail"
    BBS_LIKE = "bbs_like"
    BBS_SHARE = "bbs_share"
    BBS_REPLY = "bbs_reply"

    @classmethod
    def get_mark_name(cls, remark: str):
        mapping = {
            "签到": cls.BBS_SIGN,
            "浏览": cls.BBS_DETAIL,
            "点赞": cls.BBS_LIKE,
            "分享": cls.BBS_SHARE,
            "回复": cls.BBS_REPLY,
        }
        return next((v for k, v in mapping.items() if k in remark), None)
