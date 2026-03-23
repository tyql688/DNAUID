import random
import asyncio
from typing import Any, Dict, List, Tuple, Union, Optional

from gsuid_core.logger import logger

from ..utils import dna_api
from .reply_temps import get_random_reply
from ..utils.api.model import DNABBSTask, DNATaskProcessRes, DNACalendarSignRes
from ..utils.database.models import DNASign
from ..utils.constants.sign_target import SignTarget
from ..utils.constants.sign_bbs_mark import BBSMarkName

SIGN_STATUS = {
    True: "✅ 已完成",
    False: "❌ 未完成",
    "skip": "🚫 请勿重复签到",
    "forbidden": "🚫 签到功能已关闭",
    "failed": "❌ 签到失败",
}


def get_sign_interval():
    from ..dna_config.dna_config import DNASignConfig

    interval = DNASignConfig.get_config("SigninConcurrentNumInterval").data

    min_interval = int(interval[0])
    max_interval = int(interval[1])
    return round(random.uniform(min_interval, max_interval), 2)


def sign_concurrent_num():
    from ..dna_config.dna_config import DNASignConfig

    return DNASignConfig.get_config("SigninConcurrentNum").data


def sched_sign():
    from ..dna_config.dna_config import DNASignConfig

    return DNASignConfig.get_config("DNASchedSignin").data


def master_sign():
    from ..dna_config.dna_config import DNASignConfig

    return DNASignConfig.get_config("SigninMaster").data


def can_sign():
    from ..dna_config.dna_config import DNASignConfig

    return DNASignConfig.get_config("DNASignin").data


def can_bbs_sign():
    from ..dna_config.dna_config import DNASignConfig

    return DNASignConfig.get_config("DNABBSSignin").data


def can_bbs_task(task_name: str):
    from ..dna_config.dna_config import DNASignConfig

    return task_name in DNASignConfig.get_config("DNABBSLink").data


def get_check_config():
    from ..dna_config.dna_config import DNASignConfig

    return DNASignConfig.get_config("DNABBSLink").data


class SignService:
    ERROR_TIMES = 3

    def __init__(
        self,
        uid: str,
        token: str,
        dev_code: Optional[str] = None,
        delay: Tuple[int, int] = (0, 1),
    ):
        self.uid = uid
        self.token = token
        self.dev_code = dev_code
        self.msg_temp: Dict[str, Union[bool, str]] = {}
        self.bbs_states: Dict[str, Union[bool, str]] = {
            BBSMarkName.BBS_SIGN: False,
            BBSMarkName.BBS_DETAIL: False,
            BBSMarkName.BBS_LIKE: False,
            BBSMarkName.BBS_SHARE: False,
            BBSMarkName.BBS_REPLY: False,
        }
        self.error_msg: str = ""
        self.delay: Tuple[int, int] = delay
        self._init_status()

    def _init_status(self):
        # 可以签到则返回 False，否则返回 "forbidden"
        self.msg_temp["signed"] = False if can_sign() else "forbidden"
        self.msg_temp["bbs_signed"] = False if can_bbs_sign() else "forbidden"

    def get_auto_sign_msg(self, is_bbs: bool):
        """
        返回"禁止", 禁止
        返回"成功", 签到成功
        返回"失败", 签到失败
        """
        if is_bbs:
            if self.msg_temp["bbs_signed"] == "forbidden":
                return "禁止"
            if self.msg_temp["bbs_signed"] == "skip":
                return "请勿重复签到"
            if self.msg_temp["bbs_signed"] == "failed":
                return "签到失败"
            if self.msg_temp["bbs_signed"]:
                return "签到成功"
            else:
                return "签到失败"
        else:
            if self.msg_temp["signed"] == "forbidden":
                return "禁止"
            if self.msg_temp["signed"] == "skip":
                return "请勿重复签到"
            if self.msg_temp["signed"] == "failed":
                return "签到失败"
            if self.msg_temp["signed"]:
                return "签到成功"
            else:
                return "签到失败"

    def turn_msg(self):
        check_config = get_check_config()
        if (
            self.msg_temp["bbs_signed"] != "skip"
            and self.msg_temp["bbs_signed"] != "forbidden"
            and SignTarget.bbs_sign_complete(self.dna_sign, check_config)
        ):
            self.msg_temp["bbs_signed"] = True

        msg_list = []
        if self.msg_temp["signed"] != "forbidden":
            msg_list.append(f"签到状态: {SIGN_STATUS[self.msg_temp['signed']]}")
        if self.msg_temp["bbs_signed"] != "forbidden":
            if self.msg_temp["bbs_signed"] != "skip":
                msg_list.append("社区任务:")
                if BBSMarkName.BBS_SIGN in check_config:
                    msg_list.append(f"签到: {SIGN_STATUS[self.bbs_states[BBSMarkName.BBS_SIGN]]}")
                if BBSMarkName.BBS_DETAIL in check_config:
                    msg_list.append(f"浏览: {SIGN_STATUS[self.bbs_states[BBSMarkName.BBS_DETAIL]]}")
                if BBSMarkName.BBS_LIKE in check_config:
                    msg_list.append(f"点赞: {SIGN_STATUS[self.bbs_states[BBSMarkName.BBS_LIKE]]}")
                if BBSMarkName.BBS_SHARE in check_config:
                    msg_list.append(f"分享: {SIGN_STATUS[self.bbs_states[BBSMarkName.BBS_SHARE]]}")
                if BBSMarkName.BBS_REPLY in check_config:
                    msg_list.append(f"回复: {SIGN_STATUS[self.bbs_states[BBSMarkName.BBS_REPLY]]}")
            else:
                msg_list.append(f"社区签到: {SIGN_STATUS[self.msg_temp['bbs_signed']]}")

        if self.error_msg:
            msg_list.append(f"错误信息: {self.error_msg}")
        msg_list.append("-----------------------------")
        return "\n".join(msg_list)

    async def save_sign_data(self):
        await DNASign.upsert_dna_sign(self.dna_sign)

    async def check_status(self):
        """
        检查签到状态
        如果签到已完成（包括 True, "skip", "forbidden", "failed"），则返回 True
        如果签到未完成，则返回 False
        """
        dna_sign: Optional[DNASign] = await DNASign.get_sign_data(self.uid)
        if not dna_sign:
            self.dna_sign = DNASign.build(self.uid)
            return False
        else:
            self.dna_sign = dna_sign

        if SignTarget.game_sign_complete(self.dna_sign):
            self.msg_temp["signed"] = "skip"

        if SignTarget.bbs_sign_complete(self.dna_sign, get_check_config()):
            self.msg_temp["bbs_signed"] = "skip"

        if self.msg_temp["signed"] and self.msg_temp["bbs_signed"]:
            return True

        return False

    async def do_sign(self):
        if self.msg_temp["signed"]:
            return

        if self.dna_sign.game_sign == SignTarget.GAME_SIGN:
            return

        res = await dna_api.sign_calendar(self.token, self.dev_code)
        if not res.is_success:
            return True

        calendar_sign = DNACalendarSignRes.model_validate(res.data)
        if calendar_sign.todaySignin:
            self.msg_temp["signed"] = "skip"
            self.dna_sign.game_sign = SignTarget.GAME_SIGN
            return

        today_sign_award = calendar_sign.dayAward[calendar_sign.signinTime]

        # 开始签到
        res = await dna_api.game_sign(self.token, today_sign_award.id, today_sign_award.periodId, self.dev_code)
        if res.is_success:
            self.msg_temp["signed"] = True
            self.dna_sign.game_sign = SignTarget.GAME_SIGN
        elif res.code == 711:
            # 已签到
            self.msg_temp["signed"] = "skip"
            self.dna_sign.game_sign = SignTarget.GAME_SIGN
        else:
            self.msg_temp["signed"] = "failed"

        await asyncio.sleep(random.uniform(self.delay[0], self.delay[1]))

    async def do_bbs_sign(self):
        if self.msg_temp["bbs_signed"]:
            return

        # 获取任务进度
        res = await dna_api.get_task_process(self.token, self.dev_code)
        if not res.is_success:
            return

        task_process = DNATaskProcessRes.model_validate(res.data)
        for task in task_process.dailyTask:
            markName = task.markName
            if not markName:
                logger.warning(f"社区任务 {self.uid} {task.remark} 没有 markName: {task.model_dump_json()}")
                continue
            if not can_bbs_task(markName):
                continue
            if task.completeTimes >= task.times:
                setattr(self.dna_sign, markName, task.times)
                self.bbs_states[markName] = "skip"
                continue

            if markName == BBSMarkName.BBS_SIGN:
                await self._bbs_sign(task)
                continue

            post_list = await dna_api.get_post_list(self.token, self.dev_code)
            if not post_list.is_success or not post_list.data or not isinstance(post_list.data, dict):
                continue
            posts = post_list.data.get("postList", [])
            if not posts:
                self.error_msg = "❌ 社区任务：帖子列表为空"
                return

            if markName == BBSMarkName.BBS_DETAIL:
                await self._bbs_detail(task, posts)
            elif markName == BBSMarkName.BBS_LIKE:
                await self._bbs_like(task, posts)
            elif markName == BBSMarkName.BBS_SHARE:
                await self._bbs_share(task, posts)
            elif markName == BBSMarkName.BBS_REPLY:
                await self._bbs_reply(task, posts)

    async def _bbs_sign(self, dna_bbs_task: DNABBSTask):
        # 开始社区签到
        if self.dna_sign.bbs_sign >= SignTarget.BBS_SIGN:
            self.bbs_states[BBSMarkName.BBS_SIGN] = "skip"
            return

        res = await dna_api.bbs_sign(self.token, self.dev_code)
        if res.is_success:
            self.dna_sign.bbs_sign = SignTarget.BBS_SIGN
            self.bbs_states[BBSMarkName.BBS_SIGN] = True
        elif res.code == 10000:
            self.dna_sign.bbs_sign = SignTarget.BBS_SIGN
            self.bbs_states[BBSMarkName.BBS_SIGN] = True
        else:
            self.bbs_states[BBSMarkName.BBS_SIGN] = "failed"

        await asyncio.sleep(random.uniform(self.delay[0], self.delay[1]))

    async def _bbs_detail(self, dna_bbs_task: DNABBSTask, posts: List[Dict[str, Any]]):
        if self.dna_sign.bbs_detail >= SignTarget.BBS_DETAIL:
            self.bbs_states[BBSMarkName.BBS_DETAIL] = "skip"
            return

        need_times = dna_bbs_task.times - dna_bbs_task.completeTimes
        if need_times <= 0:
            self.bbs_states[BBSMarkName.BBS_DETAIL] = "skip"
            return

        error_times = 0
        random.shuffle(posts)
        for post in posts:
            post_id = post.get("postId")
            if not post_id:
                continue
            res = await dna_api.get_post_detail(post_id, self.token, self.dev_code)
            if res and res.is_success:
                self.dna_sign.bbs_detail += 1
            else:
                error_times += 1
                if error_times >= self.ERROR_TIMES:
                    self.error_msg = "❌ 社区任务：浏览帖子失败次数过多，请稍后重试"
                    return

            if self.dna_sign.bbs_detail >= dna_bbs_task.times:
                break

            await asyncio.sleep(random.uniform(self.delay[0], self.delay[1]))

        self.bbs_states[BBSMarkName.BBS_DETAIL] = self.dna_sign.bbs_detail >= dna_bbs_task.times

    async def _bbs_like(self, dna_bbs_task: DNABBSTask, posts: List[Dict[str, Any]]):
        if self.dna_sign.bbs_like >= SignTarget.BBS_LIKE:
            self.bbs_states[BBSMarkName.BBS_LIKE] = "skip"
            return

        need_times = dna_bbs_task.times - dna_bbs_task.completeTimes
        if need_times <= 0:
            self.bbs_states[BBSMarkName.BBS_LIKE] = "skip"
            return

        error_times = 0
        random.shuffle(posts)
        for post in posts:
            post_id = post.get("postId")
            if not post_id:
                continue
            res = await dna_api.do_like(self.token, post, self.dev_code)
            if res.is_success:
                self.dna_sign.bbs_like += 1
            else:
                error_times += 1
                if error_times >= self.ERROR_TIMES:
                    self.error_msg = "❌ 社区任务：帖子点赞失败次数过多，请稍后重试"
                    return

            if self.dna_sign.bbs_like >= dna_bbs_task.times:
                break

            await asyncio.sleep(random.uniform(self.delay[0], self.delay[1]))

        self.bbs_states[BBSMarkName.BBS_LIKE] = self.dna_sign.bbs_like >= dna_bbs_task.times

    async def _bbs_share(self, dna_bbs_task: DNABBSTask, posts: List[Dict[str, Any]]):
        if self.dna_sign.bbs_share >= SignTarget.BBS_SHARE:
            self.bbs_states[BBSMarkName.BBS_SHARE] = "skip"
            return

        res = await dna_api.do_share(self.token, self.dev_code)
        if res.is_success:
            self.dna_sign.bbs_share += 1

        self.bbs_states[BBSMarkName.BBS_SHARE] = self.dna_sign.bbs_share >= SignTarget.BBS_SHARE

    async def _bbs_reply(self, dna_bbs_task: DNABBSTask, posts: List[Dict[str, Any]]):
        if self.dna_sign.bbs_reply >= SignTarget.BBS_REPLY:
            self.bbs_states[BBSMarkName.BBS_REPLY] = "skip"
            return

        need_times = dna_bbs_task.times - dna_bbs_task.completeTimes
        if need_times <= 0:
            self.bbs_states[BBSMarkName.BBS_REPLY] = "skip"
            return

        error_times = 0
        random.shuffle(posts)
        for post in posts:
            post_id = post.get("postId")
            if not post_id:
                continue
            reply_content = get_random_reply()
            res = await dna_api.do_reply(self.token, post, reply_content, self.dev_code)
            if res.is_success:
                self.dna_sign.bbs_reply += 1
            else:
                error_times += 1
                if error_times >= self.ERROR_TIMES:
                    self.error_msg = "❌ 社区任务：帖子回复失败次数过多，请稍后重试"
                    return

            if self.dna_sign.bbs_reply >= dna_bbs_task.times:
                break

            await asyncio.sleep(random.uniform(self.delay[0] + 1, self.delay[1] + 1))

        self.bbs_states[BBSMarkName.BBS_REPLY] = self.dna_sign.bbs_reply >= dna_bbs_task.times
