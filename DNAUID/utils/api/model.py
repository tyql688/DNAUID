from typing import List, Optional

from pydantic import BaseModel, Field

from ..constants.sign_bbs_mark import BBSMarkName


class UserGame(BaseModel):
    gameId: int = Field(description="gameId", default=268)
    gameName: str = Field(description="gameName", default="二重螺旋")


class DNALoginRes(BaseModel):
    applyCancel: Optional[int] = Field(description="applyCancel", default=0)
    gender: Optional[int] = Field(description="gender", default=0)
    signature: Optional[str] = Field(description="signature", default="")
    headUrl: Optional[str] = Field(description="headUrl", default="")
    userName: Optional[str] = Field(description="userName", default="")
    userId: str = Field(description="userId")
    isOfficial: int = Field(description="isOfficial", default=0)
    token: str = Field(exclude=True, description="token")
    userGameList: List[UserGame] = Field(description="userGameList")
    isRegister: int = Field(description="isRegister", default=0)
    status: Optional[int] = Field(description="status", default=0)
    isComplete: Optional[int] = Field(
        description="isComplete 是否完成绑定 0: 未绑定, 1: 已绑定", default=0
    )
    refreshToken: str = Field(exclude=True, description="refreshToken")


class DNARoleShowVo(BaseModel):
    roleId: str = Field(description="roleId")
    headUrl: Optional[str] = Field(description="headUrl")
    level: Optional[int] = Field(description="level")
    roleName: Optional[str] = Field(description="roleName")
    isDefault: Optional[int] = Field(description="isDefault")
    roleRegisterTime: Optional[str] = Field(description="roleRegisterTime")
    boundType: Optional[int] = Field(description="boundType")
    roleBoundId: str = Field(description="roleBoundId")


class DNARole(BaseModel):
    gameName: str = Field(description="gameName")
    showVoList: List[DNARoleShowVo] = Field(description="showVoList")
    gameId: int = Field(description="gameId")


class DNARoleListRes(BaseModel):
    roles: List[DNARole] = Field(description="roles")


class DNADayAward(BaseModel):
    gameId: int = Field(description="gameId")
    periodId: int = Field(description="periodId")
    iconUrl: str = Field(description="iconUrl")
    id: int = Field(description="id")
    dayInPeriod: int = Field(description="dayInPeriod")
    updateTime: int = Field(description="updateTime")
    awardNum: int = Field(description="awardNum")
    thirdProductId: str = Field(description="thirdProductId")
    createTime: int = Field(description="createTime")
    awardName: str = Field(description="awardName")


class DNACalendarSignRes(BaseModel):
    todaySignin: bool = Field(description="todaySignin")
    dayAward: List[DNADayAward] = Field(description="dayAward")
    signinTime: int = Field(description="signinTime")


class DNABBSTask(BaseModel):
    remark: str = Field(description="备注")
    completeTimes: int = Field(description="完成次数")
    times: int = Field(description="需要次数")
    skipType: int = Field(description="skipType")
    gainExp: int = Field(description="获取经验")
    process: float = Field(description="进度")
    gainGold: int = Field(description="获取金币")

    # 添加markName字段
    markName: Optional[str] = Field(default=None, description="任务标识名")

    def __init__(self, **data):
        remark = data.get("remark", "")
        data["markName"] = BBSMarkName.get_mark_name(remark)
        super().__init__(**data)


class DNATaskProcessRes(BaseModel):

    dailyTask: List[DNABBSTask] = Field(description="dailyTask")
    # growTask: List[DNABBSTask] = Field(description="growTask")
