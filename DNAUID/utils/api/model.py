from typing import Any, List, Literal, Optional

from pydantic import Field, BaseModel, model_validator

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
    dNum: Optional[str] = Field(description="dNum", default="")
    userId: str = Field(description="userId")
    isOfficial: int = Field(description="isOfficial", default=0)
    token: str = Field(exclude=True, description="token")
    userGameList: List[UserGame] = Field(description="userGameList")
    isRegister: int = Field(description="isRegister", default=0)
    status: Optional[int] = Field(description="status", default=0)
    isComplete: Optional[int] = Field(description="isComplete 是否完成绑定 0: 未绑定, 1: 已绑定", default=0)
    refreshToken: str = Field(exclude=True, description="refreshToken")


class DNATokenPayload(BaseModel):
    userId: str | int = Field(description="社区用户ID")


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

    mh_type: Optional[Literal["role", "weapon", "mzx"]] = Field(description="mh_type", default=None)


class DraftDoingInfo(BaseModel):
    draftCompleteNum: int = Field(description="draftCompleteNum")
    draftDoingNum: int = Field(description="draftDoingNum")
    # 空槽 / 异常状态时后端可能不返回 endTime / productName / productId
    endTime: Optional[str] = Field(description="结束时间", default=None)
    productId: Optional[int] = Field(description="productId", default=None)
    productName: Optional[str] = Field(description="productName", default=None)
    startTime: str = Field(description="开始时间")


class DraftInfo(BaseModel):
    draftDoingInfo: Optional[List[DraftDoingInfo]] = Field(description="draftDoingInfo", default=None)
    draftDoingNum: int = Field(description="正在做的锻造")
    draftMaxNum: int = Field(description="最大锻造数量")


class DNAWeeklyReportItem(BaseModel):
    icon: str = Field(description="资源图标 URL")
    itemId: int = Field(description="资源 ID")
    itemName: str = Field(description="资源名")
    quality: int = Field(description="品质 1-5", default=1)
    totalNum: str = Field(description="累计获取数量", default="0")


class DNAWeeklyReportCategory(BaseModel):
    categoryName: str = Field(description="分类名")
    isBase: Optional[bool] = Field(description="是否基础资源", default=False)
    items: List[DNAWeeklyReportItem] = Field(description="资源列表")
    type: int = Field(description="分类类型")


class DNAItemWeeklyReportRes(BaseModel):
    categories: List[DNAWeeklyReportCategory] = Field(description="分类资源")
    startDate: str = Field(description="周开始日期 YYYYMMDD")
    endDate: str = Field(description="周结束日期 YYYYMMDD")
    weekType: int = Field(description="1=本周 2=上周")


class DNARoleShortNoteRes(BaseModel):
    rougeLikeRewardCount: int = Field(description="迷津进度")
    rougeLikeRewardTotal: int = Field(description="迷津总数")
    currentTaskProgress: int = Field(description="备忘手记进度")
    maxDailyTaskProgress: int = Field(description="备忘手记总数")
    hardBossRewardCount: int = Field(description="梦魇进度")
    hardBossRewardTotal: int = Field(description="梦魇总数")
    dungeonReward: int = Field(description="竞逐进度")
    dungeonRewardTotal: int = Field(description="竞逐总数")
    draftInfo: DraftInfo = Field(description="锻造信息")


class WeaponInsForTool(BaseModel):
    elementIcon: str = Field(description="武器类型图标")
    icon: str = Field(description="武器图标")
    level: int = Field(description="武器等级")
    name: str = Field(description="武器名称")
    unLocked: bool = Field(description="是否解锁")
    weaponEid: Optional[str] = Field(description="weaponEid", default=None)
    weaponId: int = Field(description="weaponId")
    skillLevel: int = Field(description="武器精炼等级", default=0)


class RoleInsForTool(BaseModel):
    charEid: Optional[str] = Field(description="charEid", default=None)
    charId: int = Field(description="charId")
    elementIcon: str = Field(description="元素图标")
    gradeLevel: int = Field(description="命座等级")
    icon: str = Field(description="角色图标")
    level: int = Field(description="角色等级")
    name: str = Field(description="角色名称")
    unLocked: bool = Field(description="是否解锁")


class RoleAchievement(BaseModel):
    paramKey: str = Field(description="paramKey")
    paramValue: str = Field(description="paramValue")


class RoleAchv(BaseModel):
    total: int = Field(description="总成就数")


class RoleShowForTool(BaseModel):
    roleChars: List[RoleInsForTool] = Field(description="角色列表")
    langRangeWeapons: List[WeaponInsForTool] = Field(description="武器列表")
    closeWeapons: List[WeaponInsForTool] = Field(description="武器列表")
    level: int = Field(description="等级")
    params: List[RoleAchievement] = Field(description="成就列表")
    roleId: str = Field(description="角色id")
    roleName: str = Field(description="角色名称")
    roleAchv: RoleAchv = Field(description="成就信息")


class RoleInfoForTool(BaseModel):
    # abyssInfo:
    roleShow: RoleShowForTool = Field(description="角色信息")


class DNARoleForToolRes(BaseModel):
    roleInfo: RoleInfoForTool = Field(description="角色信息")


class DNAMHRes(BaseModel):
    instanceInfo: List[DNARoleForToolInstanceInfo] = Field(description="instanceInfo")

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, values: Any):
        # 兼容列表输入
        if isinstance(values, list):
            values = {"instanceInfo": values}

        instanceInfo = values.get("instanceInfo", [])
        for index, instance in enumerate(instanceInfo):
            if index == 0:
                instance["mh_type"] = "role"
            elif index == 1:
                instance["mh_type"] = "weapon"
            elif index == 2:
                instance["mh_type"] = "mzx"

        return values


class RoleAttribute(BaseModel):
    skillRange: str = Field(description="技能范围")
    strongValue: str = Field(description="strongValue")
    skillIntensity: str = Field(description="技能威力")
    weaponTags: List[Optional[str]] = Field(description="武器精通")
    defense: int = Field(description="防御", alias="def")
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
    icon: str = Field(description="溯源图标")
    description: str = Field(description="溯源描述")


class Mode(BaseModel):
    id: int = Field(description="id 没佩戴为-1")
    icon: Optional[str] = Field(description="图标", default=None)
    quality: Optional[int] = Field(description="质量", default=None)
    name: Optional[str] = Field(description="名称", default=None)
    level: Optional[int] = Field(description="等级", default=0)


class RoleDetail(BaseModel):
    attribute: RoleAttribute = Field(description="角色属性")
    skills: List[RoleSkill] = Field(description="角色技能")
    paint: str = Field(description="立绘")
    charId: int = Field(description="角色配置ID")
    charName: str = Field(description="角色名称")
    elementIcon: str = Field(description="元素图标")
    traces: List[RoleTrace] = Field(description="溯源")
    currentVolume: int = Field(description="当前魔之楔")
    sumVolume: int = Field(description="最大魔之楔")
    level: int = Field(description="角色等级")
    icon: str = Field(description="角色头像")
    gradeLevel: int = Field(description="溯源等级 0-6")
    elementName: str = Field(description="元素名称")
    modes: List[Mode] = Field(description="mode")
    conWeaponEid: Optional[str] = Field(description="同律武器eid", default=None)
    conWeaponId: Optional[int] = Field(description="同律武器id", default=None)


class DNARoleDetailRes(BaseModel):
    charDetail: RoleDetail = Field(description="角色详情")


class WeaponAttribute(BaseModel):
    atk: int = Field(description="攻击")
    crd: float = Field(description="暴击率")
    cri: float = Field(description="暴击伤害")
    speed: float = Field(description="攻击速度")
    trigger: float = Field(description="触发率")


class WeaponDetail(BaseModel):
    attribute: WeaponAttribute = Field(description="武器属性")
    currentVolume: int = Field(description="当前魔之楔")
    elementIcon: str = Field(description="元素图标")
    elementName: str = Field(description="元素名称")
    icon: str = Field(description="武器头像")
    id: int = Field(description="武器id")
    level: int = Field(description="武器等级")
    modes: List[Mode] = Field(description="mode")
    name: str = Field(description="武器名称")
    skillLevel: int = Field(description="武器精炼等级")
    sumVolume: int = Field(description="最大魔之楔")


class DNAWeaponDetailRes(BaseModel):
    weaponDetail: WeaponDetail = Field(description="武器详情")


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
    # 当日尚未签到 / 账号未绑定角色时, 后端可能只回 period + dayAward + continueAward,
    # 顶层签到状态字段和 roleInfo 全部省略 -> 这里允许它们缺失, 由调用方判空再决定走签到还是渲染.
    todaySignin: Optional[bool] = Field(description="todaySignin", default=None)
    userGoldNum: Optional[int] = Field(description="userGoldNum", default=None)
    dayAward: List[DNADayAward] = Field(description="dayAward", default_factory=list)
    signinTime: Optional[int] = Field(description="signinTime", default=None)
    period: DNACaSignPeriod = Field(description="period")
    roleInfo: Optional[DNACaSignRoleInfo] = Field(description="roleInfo", default=None)


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


class WikiDetail(BaseModel):
    name: str = Field(description="name")


class DNAWikiRes(BaseModel):
    wikis: List[WikiDetail] = Field(description="wikis")
