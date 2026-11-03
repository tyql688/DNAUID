from __future__ import annotations

import asyncio
from typing import TypeVar, Annotated
from datetime import datetime
from dataclasses import dataclass

import httpx
from pydantic import Field, BaseModel, JsonValue, ConfigDict, TypeAdapter, BeforeValidator, field_validator
from pydantic_core import PydanticUseDefault
from dna_builder_sdk.calc.gamedata import GameDataTables

from gsuid_core.logger import logger

from ..utils.dob import records
from ..utils.dob.pack import get_tables
from ..utils.api.model import Mode, RoleSkill, RoleDetail, WeaponDetail, RoleAttribute, WeaponAttribute
from ..utils.dob.build import WeaponSlot
from ..utils.dob.panel import PanelView, compute_panel
from ..utils.dob.engine import DobEngine, DobBuildError, open_engine
from ..utils.name_convert import id2name_data
from ..utils.constants.constants import DOB_CDN

CHAR_BUILD_LIMIT = 10
GRAPHQL_URL = "https://api.dna-builder.cn/graphql"
_BUILD_FIELDS = "id title charId charSettings updateAt likes views user{name qq}"
_BOARDS_QUERY = "{rankingLists{name items{build{" + _BUILD_FIELDS + "}}}}"
_CHAR_BUILDS_QUERY = "query($c:Int,$l:Int,$sb:String){builds(charId:$c,limit:$l,sortBy:$sb){" + _BUILD_FIELDS + "}}"
_BUILD_QUERY = "query($id:String!){build(id:$id){" + _BUILD_FIELDS + "}}"
# DOB 构筑的 8 个角色槽 → 官方 modes 下标
_CHAR_SLOT_TO_MODE = (0, 2, 3, 1, 6, 4, 7, 5)
_WEAPON_MOD_SLOTS = 8
_SKILL_WEAPON_MOD_SLOTS = 4

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class DobFetchError(RuntimeError):
    """DOB 线上数据拉取或解析失败。"""


class _DobModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


ModSlot = tuple[int, int] | None
_SETTINGS = TypeAdapter(dict[str, JsonValue])


class _SettingsModel(_DobModel):
    @field_validator("*", mode="before")
    @classmethod
    def null_uses_default(cls, value: JsonValue) -> JsonValue:
        if value is None:
            raise PydanticUseDefault
        return value


class _ModVariant(_SettingsModel):
    char: list[ModSlot] = Field(default_factory=list, alias="角色")
    melee: list[ModSlot] = Field(default_factory=list, alias="近战")
    ranged: list[ModSlot] = Field(default_factory=list, alias="远程")
    skill: list[ModSlot] = Field(default_factory=list, alias="同律")
    aura: int | None = Field(default=None, alias="中枢")


class _BuildSettings(_SettingsModel):
    charLevel: int = 80
    meleeWeapon: int = 10206
    rangedWeapon: int = 20102
    meleeWeaponLevel: int = 80
    rangedWeaponLevel: int = 80
    meleeWeaponRefine: int = 5
    rangedWeaponRefine: int = 5
    charMods: list[ModSlot] = Field(default_factory=list)
    meleeMods: list[ModSlot] = Field(default_factory=list)
    rangedMods: list[ModSlot] = Field(default_factory=list)
    skillWeaponMods: list[ModSlot] = Field(default_factory=list)
    auraMod: int = 31524
    modVariantIndex: int = 0
    modVariants: list[_ModVariant | None] = Field(default_factory=list)

    def slots(self) -> tuple[list[ModSlot], list[ModSlot], list[ModSlot], list[ModSlot], int]:
        char, melee, ranged, skill, aura = (
            self.charMods,
            self.meleeMods,
            self.rangedMods,
            self.skillWeaponMods,
            self.auraMod,
        )
        if 1 <= self.modVariantIndex <= len(self.modVariants):
            variant = self.modVariants[self.modVariantIndex - 1]
            if variant is not None:
                char, melee, ranged, skill = variant.char, variant.melee, variant.ranged, variant.skill
                aura = variant.aura if variant.aura is not None and variant.aura > 0 else aura
        return char, melee, ranged, skill, aura


class _SkillRecord(_DobModel):
    name: str = Field(alias="名称")
    icon: str = ""


class _CharRecord(_DobModel):
    name: str = Field(alias="名称")
    element: str = Field(alias="属性")
    skills: list[_SkillRecord] = Field(alias="技能")


class _WeaponRecord(_DobModel):
    id: int
    name: str = Field(alias="名称")
    icon: str
    skill: list[int] = Field(default_factory=lambda: [1])


class _ModRecord(_DobModel):
    icon: str


class DobUser(_DobModel):
    # 没填的作者信息接口给 null，解析时就换成默认值
    name: Annotated[str, BeforeValidator(lambda value: "匿名" if value is None else value)] = "匿名"
    qq: Annotated[str, BeforeValidator(lambda value: "" if value is None else value)] = ""


class DobBuildInfo(_DobModel):
    id: str
    title: str
    charId: int
    charSettings: str
    updateAt: float
    likes: int
    views: int
    user: Annotated[DobUser, BeforeValidator(lambda value: {} if value is None else value)] = Field(
        default_factory=DobUser
    )


class DobRankingItem(_DobModel):
    build: DobBuildInfo | None = None


class DobRankingList(_DobModel):
    name: str
    items: list[DobRankingItem]


class _BuildsData(_DobModel):
    builds: list[DobBuildInfo]


class _BoardsData(_DobModel):
    rankingLists: list[DobRankingList]


class _BuildData(_DobModel):
    build: DobBuildInfo | None = None


class _GraphQLError(_DobModel):
    message: str


class _GraphQLBody(_DobModel):
    data: dict[str, JsonValue] | None = None
    errors: list[_GraphQLError] = Field(default_factory=list)


@dataclass(frozen=True, slots=True, kw_only=True)
class BuildScore:
    target_fn: str
    dps: int


@dataclass(frozen=True, slots=True, kw_only=True)
class BuildFailure:
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class BuildRow:
    """榜单 / 角色构筑列表的一行。"""

    rank: int | None
    bdid: str
    char_id: int
    char_name: str
    head_url: str | None
    title: str
    author: str
    author_qq: str
    update_at: str
    score: BuildScore | BuildFailure


@dataclass(frozen=True, slots=True, kw_only=True)
class Board:
    name: str
    rows: list[BuildRow]


@dataclass(frozen=True, slots=True, kw_only=True)
class BuildCard:
    """单构筑卡：装配结果 + 构筑信息。"""

    role: RoleDetail
    panel: PanelView
    bdid: str
    title: str
    author: str
    author_qq: str
    target_fn: str
    target_value: str
    likes: int
    views: int


async def _query(model: type[_ModelT], query: str, variables: dict[str, str | int]) -> _ModelT:
    # ValidationError 与 JSON 解码错误都是 ValueError
    try:
        # 每次新建：mock 宿主与测试会跨事件循环调用，共用连接池会碰到已关闭的 loop
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(GRAPHQL_URL, json={"query": query, "variables": variables})
        response.raise_for_status()
        body = _GraphQLBody.model_validate(response.json())
        if body.errors:
            raise DobFetchError(f"DOB 数据获取失败：{body.errors[0].message}")
        return model.model_validate(body.data)
    except (httpx.HTTPError, ValueError) as error:
        raise DobFetchError(f"DOB 数据获取失败：{error!r}") from error


def _cdn_icon(kind: str, icon: str) -> str:
    return f"{DOB_CDN}/imgs/webp/T_{kind}_{icon}.webp"


def bot_char_name(char_id: int) -> str:
    """bot 别名库里的角色名，能被指令解析回来。"""
    return id2name_data.get(str(char_id), f"ID:{char_id}")


def char_display_name(char_id: int) -> str:
    record = records.char_record(char_id)
    return record["名称"] if record else bot_char_name(char_id)


def fmt_target_value(value: float) -> str:
    """目标值格式化：7.40亿 / 3.2万。"""
    if value >= 1e8:
        return f"{value / 1e8:.2f}亿"
    if value >= 1e4:
        return f"{value / 1e4:.1f}万"
    return f"{int(value)}"


def _settings(build: DobBuildInfo) -> tuple[_BuildSettings, dict[str, JsonValue]]:
    try:
        raw = _SETTINGS.validate_json(build.charSettings)
        settings = _BuildSettings.model_validate(raw)
    except ValueError as error:
        raise DobBuildError(f"构筑设置无法解析：{error}") from error
    return settings, raw | _SETTINGS.validate_python(settings.model_dump(mode="json", by_alias=True))


def _recalc(build: DobBuildInfo, tables: GameDataTables) -> BuildScore | BuildFailure:
    """本地重算目标值；失败保留原因，由榜单单独展示。"""
    try:
        _, settings = _settings(build)
        with open_engine(build.charId, settings, tables) as engine:
            target, value = engine.calculate()
    except DobBuildError as error:
        logger.warning(f"[DOB] 构筑 {build.id} DPS 重算失败: {error!r}")
        return BuildFailure(reason=str(error))
    return BuildScore(target_fn=target, dps=round(value))


def _rows(builds: list[DobBuildInfo], *, by_dps: bool) -> list[BuildRow]:
    tables = get_tables()
    scored = [(build, _recalc(build, tables)) for build in builds]
    if by_dps:
        scored.sort(key=lambda item: (0, -item[1].dps) if isinstance(item[1], BuildScore) else (1, 0))
    rows: list[BuildRow] = []
    for rank, (build, score) in enumerate(scored, start=1):
        record = records.char_record(build.charId)
        rows.append(
            BuildRow(
                rank=None if by_dps and isinstance(score, BuildFailure) else rank,
                bdid=build.id,
                char_id=build.charId,
                char_name=char_display_name(build.charId),
                head_url=_cdn_icon("Head", record["icon"]) if record else None,
                title=build.title,
                author=build.user.name,
                author_qq=build.user.qq,
                update_at=datetime.fromtimestamp(build.updateAt / 1000).strftime("%Y-%m-%d %H:%M"),
                score=score,
            )
        )
    return rows


def _boards(rankings: list[DobRankingList]) -> list[Board]:
    return [
        Board(
            name=ranking.name,
            rows=_rows([item.build for item in ranking.items if item.build is not None], by_dps=True),
        )
        for ranking in rankings
    ]


async def fetch_boards() -> list[Board]:
    """全部榜单，按本地重算的 DPS 降序（构筑已删除的席位跳过）。"""
    rankings = (await _query(_BoardsData, _BOARDS_QUERY, {})).rankingLists
    # 每席都要引擎重算，CPU 活放线程池
    return await asyncio.to_thread(_boards, rankings)


async def fetch_char_builds(char_id: int) -> list[BuildRow]:
    """某角色点赞最多的构筑，序号即点赞排名。"""
    data = await _query(_BuildsData, _CHAR_BUILDS_QUERY, {"c": char_id, "l": CHAR_BUILD_LIMIT, "sb": "likes"})
    return await asyncio.to_thread(_rows, data.builds, by_dps=False)


def _mode(entry: ModSlot) -> Mode:
    """构筑的魔之楔 ID 与等级 → 角色卡 Mode；空槽 id=-1。"""
    if entry is None:
        return Mode(id=-1, level=0)
    mod_id, level = entry
    record = records.mod_record(mod_id)
    return Mode(
        id=mod_id,
        level=level,
        name=records.mod_name(mod_id),
        icon=_cdn_icon("Mod", _ModRecord.model_validate(record).icon) if record is not None else None,
        quality=records.mod_quality(mod_id),
    )


def _weapon_detail(record: _WeaponRecord, level: int, refine: int, mods: list[ModSlot], slots: int) -> WeaponDetail:
    """数据包武器条目与构筑设置 → WeaponDetail，魔之楔补齐到 slots 槽。"""
    padded = [*mods, *[None] * (slots - len(mods))][:slots]
    return WeaponDetail(
        attribute=WeaponAttribute(atk=0, crd=0.0, cri=0.0, speed=0.0, trigger=0.0),
        currentVolume=0,
        icon=_cdn_icon("Head", record.icon),
        id=record.id,
        level=level,
        modes=[_mode(entry) for entry in padded],
        name=record.name,
        skillLevel=refine,
        sumVolume=0,
    )


def _weapon(weapon_id: int, level: int, refine: int, mods: list[ModSlot]) -> WeaponDetail | None:
    """近战 / 远程武器；没带或数据包未收录返回 None。"""
    if weapon_id == 0:
        return None
    record = records.weapon_record(weapon_id)
    if record is None:
        return None
    return _weapon_detail(_WeaponRecord.model_validate(record), level, refine, mods, _WEAPON_MOD_SLOTS)


def _skill_weapon(engine: DobEngine, settings: _BuildSettings, mods: list[ModSlot]) -> WeaponDetail | None:
    """同律武器：条目挂在角色下，角色没有同律武器返回 None。"""
    raw = records.con_weapon_record(engine.char_id)
    # 继承型（芙罗拉/刻舟/煜明）没有图标和魔之楔，面板就是近战武器的，不单独画
    if raw is None or "inherit" in raw:
        return None
    record = _WeaponRecord.model_validate(raw)
    index = next((i for i in record.skill if i >= 0), 2)
    level = engine.skill_levels[min(index, 2)][1]
    return _weapon_detail(record, settings.charLevel, level, mods, _SKILL_WEAPON_MOD_SLOTS)


def _role(engine: DobEngine, settings: _BuildSettings, char_slots: list[ModSlot], aura: int) -> RoleDetail:
    """按构筑设置合成角色卡，基础属性取同等级空装备面板。"""
    char_id = engine.char_id
    char = _CharRecord.model_validate(records.char_record(char_id))
    char_mods = list(char_slots)
    char_mods += [None] * (len(_CHAR_SLOT_TO_MODE) - len(char_mods))
    modes = [_mode(char_mods[_CHAR_SLOT_TO_MODE.index(index)]) for index in range(len(_CHAR_SLOT_TO_MODE))]
    modes.append(_mode((aura, 10) if aura else None))
    skill_icons = {skill.name: skill.icon for skill in char.skills if skill.icon}
    base_settings: dict[str, JsonValue] = {
        "charLevel": settings.charLevel,
        "charSkillLevel": engine.settings["charSkillLevel"],
        "resonanceGain": 0,
        "meleeWeapon": 0,
        "rangedWeapon": 0,
        "auraMod": 0,
    }
    with open_engine(char_id, base_settings, get_tables()) as base_engine:
        base = base_engine.char_panel()
    return RoleDetail(
        attribute=RoleAttribute.model_validate(
            {
                "atk": int(base["攻击"]),
                "maxHp": int(base["生命"]),
                "maxES": int(base["护盾"]),
                "def": int(base["防御"]),
                "maxSp": int(base["神智"]),
                "skillIntensity": f"{base['技能威力'] * 100:g}%",
                "skillRange": f"{base['技能范围'] * 100:g}%",
                "skillSustain": f"{base['技能耐久'] * 100:g}%",
                "skillEfficiency": f"{base['技能效益'] * 100:g}%",
                "skillRecharge": "",
                "strongValue": "0",
                "enmityValue": "0",
                "weaponTags": [],
            }
        ),
        skills=[
            RoleSkill(
                skillId=0,
                icon=_cdn_icon("Skill", skill_icons[name]) if name in skill_icons else "",
                level=level,
                skillName=name,
            )
            for name, level in engine.skill_levels
        ],
        paint="",
        charId=char_id,
        charName=char.name,
        elementIcon="",
        traces=[],
        currentVolume=0,
        sumVolume=0,
        level=settings.charLevel,
        icon="",
        gradeLevel=0,
        elementName=char.element,
        modes=modes,
    )


async def synthesize_build(bdid: str) -> BuildCard | None:
    """线上构筑 → 角色卡数据；构筑不存在返回 None。"""
    info = (await _query(_BuildData, _BUILD_QUERY, {"id": bdid})).build
    if info is None:
        return None
    return await asyncio.to_thread(_synthesize_build, info)


def _synthesize_build(info: DobBuildInfo) -> BuildCard:
    settings, raw_settings = _settings(info)
    with open_engine(info.charId, raw_settings, get_tables()) as engine:
        target_fn, target_value = engine.calculate()
        char_mods, melee_mods, ranged_mods, skill_mods, aura = settings.slots()
        candidates = (
            (
                WeaponSlot.MELEE,
                _weapon(settings.meleeWeapon, settings.meleeWeaponLevel, settings.meleeWeaponRefine, melee_mods),
            ),
            (
                WeaponSlot.RANGED,
                _weapon(settings.rangedWeapon, settings.rangedWeaponLevel, settings.rangedWeaponRefine, ranged_mods),
            ),
            (WeaponSlot.SKILL, _skill_weapon(engine, settings, skill_mods)),
        )
        weapons = {slot: weapon for slot, weapon in candidates if weapon is not None}
        role = _role(engine, settings, char_mods, aura)
        panel = compute_panel(engine, role, weapons)
    return BuildCard(
        role=role,
        panel=panel,
        bdid=info.id,
        title=info.title,
        author=info.user.name,
        author_qq=info.user.qq,
        target_fn=target_fn,
        target_value=fmt_target_value(target_value),
        likes=info.likes,
        views=info.views,
    )
