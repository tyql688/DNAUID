from typing import List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl

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


class DNARoleForToolInstance(BaseModel):
    id: int = Field(description="id")
    name: str = Field(description="name")


class DNARoleForToolInstanceInfo(BaseModel):
    instances: List[DNARoleForToolInstance] = Field(description="instances")

    mh_type: Optional[Literal["role", "weapon", "mzx"]] = Field(
        description="mh_type", default=None
    )


class WeaponInsForTool(BaseModel):
    elementIcon: HttpUrl = Field(description="武器类型图标")
    icon: HttpUrl = Field(description="武器图标")
    level: int = Field(description="武器等级")
    name: str = Field(description="武器名称")
    unLocked: bool = Field(description="是否解锁")
    weaponEid: Optional[str] = Field(description="weaponEid", default=None)
    weaponId: int = Field(description="weaponId")
    # skillLevel: Optional[int] = Field(description="skillLevel")


class RoleInsForTool(BaseModel):
    charEid: Optional[str] = Field(description="charEid", default=None)
    charId: int = Field(description="charId")
    elementIcon: HttpUrl = Field(description="元素图标")
    gradeLevel: int = Field(description="命座等级")
    icon: HttpUrl = Field(description="角色图标")
    level: int = Field(description="角色等级")
    name: str = Field(description="角色名称")
    unLocked: bool = Field(description="是否解锁")


class RoleAchievement(BaseModel):
    paramKey: str = Field(description="paramKey")
    paramValue: str = Field(description="paramValue")


class RoleShowForTool(BaseModel):
    roleChars: List[RoleInsForTool] = Field(description="角色列表")
    langRangeWeapons: List[WeaponInsForTool] = Field(description="武器列表")
    closeWeapons: List[WeaponInsForTool] = Field(description="武器列表")
    level: int = Field(description="等级")
    params: List[RoleAchievement] = Field(description="成就列表")
    roleId: str = Field(description="角色id")
    roleName: str = Field(description="角色名称")


class RoleInfoForTool(BaseModel):
    # abyssInfo:
    roleShow: RoleShowForTool = Field(description="角色信息")


class DNARoleForToolRes(BaseModel):
    instanceInfo: List[DNARoleForToolInstanceInfo] = Field(description="instanceInfo")
    roleInfo: RoleInfoForTool = Field(description="角色信息")

    def __init__(self, **data):
        instanceInfo = data.get("instanceInfo", [])
        for index, instance in enumerate(instanceInfo):
            if index == 0:
                instance["mh_type"] = "role"
            elif index == 1:
                instance["mh_type"] = "weapon"
            elif index == 2:
                instance["mh_type"] = "mzx"
        super().__init__(**data)


class RoleAttribute(BaseModel):
    skillRange: str = Field(description="技能范围")
    strongValue: str = Field(description="strongValue")
    skillIntensity: str = Field(description="技能威力")
    weaponTags: List[str] = Field(description="武器精通")
    defense: int = Field(description="def", alias="防御")
    enmityValue: str = Field(description="enmityValue")
    skillEfficiency: str = Field(description="技能效益")
    skillSustain: str = Field(description="技能耐久")
    maxHp: int = Field(description="最大生命值")
    atk: int = Field(description="攻击")
    maxES: int = Field(description="护盾")
    maxSp: int = Field(description="最大神志")


class RoleSkill(BaseModel):
    skillId: int = Field(description="技能id")
    icon: str = Field(description="技能图标")
    level: int = Field(description="技能等级")
    skillName: str = Field(description="技能名称")


class RoleTrace(BaseModel):
    icon: HttpUrl = Field(description="溯源图标")
    description: str = Field(description="溯源描述")


class Mode(BaseModel):
    id: int = Field(description="id 没佩戴为-1")
    icon: Optional[HttpUrl] = Field(description="图标")
    quality: Optional[int] = Field(description="质量")
    name: Optional[str] = Field(description="名称")


class RoleDetail(BaseModel):
    attribute: RoleAttribute = Field(description="角色属性")
    skills: List[RoleSkill] = Field(description="角色技能")
    paint: HttpUrl = Field(description="立绘")
    charName: str = Field(description="角色名称")
    elementIcon: HttpUrl = Field(description="元素图标")
    traces: List[RoleTrace] = Field(description="溯源")
    currentVolume: int = Field(description="当前魔之楔")
    maxVolume: int = Field(description="最大魔之楔")
    level: int = Field(description="角色等级")
    icon: HttpUrl = Field(description="角色头像")
    gradeLevel: int = Field(description="溯源等级 0-6")
    elementName: str = Field(description="元素名称")
    modes: List[Mode] = Field(description="mode")


class DNARoleDetailRes(BaseModel):
    charDetail: RoleDetail = Field(description="角色详情")


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


class DNACaSignPeriod(BaseModel):
    gameId: int = Field(description="gameId")
    retryCos: int = Field(description="retryCos")
    endDate: int = Field(description="endDate")
    id: int = Field(description="id")
    startDate: int = Field(description="startDate")
    retryTimes: int = Field(description="retryTimes")
    overDays: int = Field(description="overDays")
    createTime: int = Field(description="createTime")
    name: str = Field(description="name")


class DNACaSignRoleInfo(BaseModel):
    headUrl: str = Field(description="headUrl")
    roleId: str = Field(description="roleId")
    roleName: str = Field(description="roleName")
    level: int = Field(description="level")
    roleBoundId: str = Field(description="roleBoundId")


class DNACalendarSignRes(BaseModel):
    todaySignin: bool = Field(description="todaySignin")
    userGoldNum: int = Field(description="userGoldNum")
    dayAward: List[DNADayAward] = Field(description="dayAward")
    signinTime: int = Field(description="signinTime")
    period: DNACaSignPeriod = Field(description="period")
    roleInfo: DNACaSignRoleInfo = Field(description="roleInfo")


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
