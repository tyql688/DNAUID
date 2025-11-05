from typing import List

from ..database.models import DNASign


class SignTarget:
    # 游戏签到目标
    GAME_SIGN = 1  # 游戏签到

    # 社区签到目标
    BBS_SIGN = 1  # 社区签到
    BBS_DETAIL = 3  # 社区浏览
    BBS_LIKE = 5  # 社区点赞
    BBS_SHARE = 1  # 社区分享
    BBS_REPLY = 5  # 社区回复

    @classmethod
    def game_sign_complete(cls, dna_sign: "DNASign") -> bool:
        return cls.GAME_SIGN == dna_sign.game_sign

    @classmethod
    def bbs_sign_complete(
        cls,
        dna_sign: "DNASign",
        check_config: List[str],
    ) -> bool:
        from .sign_bbs_mark import BBSMarkName

        for config in check_config:
            if config == BBSMarkName.BBS_SIGN:
                if dna_sign.bbs_sign < cls.BBS_SIGN:
                    return False
            elif config == BBSMarkName.BBS_DETAIL:
                if dna_sign.bbs_detail < cls.BBS_DETAIL:
                    return False
            elif config == BBSMarkName.BBS_LIKE:
                if dna_sign.bbs_like < cls.BBS_LIKE:
                    return False
            elif config == BBSMarkName.BBS_SHARE:
                if dna_sign.bbs_share < cls.BBS_SHARE:
                    return False
            elif config == BBSMarkName.BBS_REPLY:
                if dna_sign.bbs_reply < cls.BBS_REPLY:
                    return False
        return True
