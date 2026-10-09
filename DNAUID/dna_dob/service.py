from __future__ import annotations

import json
import asyncio
from typing import TypeVar, Annotated
from datetime import datetime
from dataclasses import dataclass

import httpx
from pydantic import Field, BaseModel, JsonValue, ConfigDict, BeforeValidator
from dna_builder_sdk.calc import Engine, build_state
from dna_builder_sdk.calc.gamedata import GameDataTables

from gsuid_core.logger import logger

from ..utils.dob import records
from ..utils.dob.pack import get_tables
from ..utils.api.model import Mode, RoleSkill, RoleDetail, WeaponDetail, RoleAttribute, WeaponAttribute
from ..utils.dob.build import DobBuild, WeaponSlot, DobBuildError
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
class BuildRow:
    """榜单 / 角色构筑列表的一行。"""

    rank: int
    bdid: str
    char_id: int
    char_name: str
    head_url: str | None
    title: str
    author: str
    author_qq: str
    update_at: str
    target_fn: str
    dps: int


@dataclass(frozen=True, slots=True, kw_only=True)
class Board:
    name: str
    rows: list[BuildRow]


@dataclass(frozen=True, slots=True, kw_only=True)
class BuildCard:
    """单构筑卡：装配结果 + 构筑信息。"""

    build: DobBuild
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


def _recalc(build: DobBuildInfo, tables: GameDataTables) -> tuple[str, int]:
    """引擎本地重算 DPS（与网页榜单同口径），返回 (目标函数, DPS)，算不出记 0。"""
    # 设置是用户上传的、引擎是三方库，异常面无法枚举：单行兜住留日志，不拖垮整张榜
    try:
        engine = Engine(build_state(build.charId, json.loads(build.charSettings), tables), tables)
        value = engine.calculate()
    except Exception as error:
        logger.warning(f"[DOB] 构筑 {build.id} DPS 重算失败: {error!r}")
        return "-", 0
    return engine.s["targetFunction"], round(value)


def _rows(builds: list[DobBuildInfo], *, by_dps: bool) -> list[BuildRow]:
    tables = get_tables()
    scored = [(build, *_recalc(build, tables)) for build in builds]
    if by_dps:
        scored.sort(key=lambda item: item[2], reverse=True)
    rows: list[BuildRow] = []
    for rank, (build, target_fn, dps) in enumerate(scored, start=1):
        record = records.char_record(build.charId)
        rows.append(
            BuildRow(
                rank=rank,
                bdid=build.id,
                char_id=build.charId,
                char_name=char_display_name(build.charId),
                head_url=_cdn_icon("Head", record["icon"]) if record else None,
                title=build.title,
                author=build.user.name,
                author_qq=build.user.qq,
                update_at=datetime.fromtimestamp(build.updateAt / 1000).strftime("%Y-%m-%d %H:%M"),
                target_fn=target_fn,
                dps=dps,
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


def _mode(entry: dict | None) -> Mode:
    """引擎状态里的 mod 实例 → 角色卡 Mode；空槽 id=-1。"""
    if entry is None:
        return Mode(id=-1, level=0)
    mod_id = entry["id"]
    record = records.mod_record(mod_id)
    return Mode(
        id=mod_id,
        level=entry["_等级"],
        name=records.mod_name(mod_id),
        icon=_cdn_icon("Mod", record["icon"]) if record else None,
        quality=records.mod_quality(mod_id),
    )


def _weapon_detail(record: dict, level: int, refine: int, mods: list[dict | None], slots: int) -> WeaponDetail:
    """数据包武器条目 + 引擎里的等级与魔之楔 → 角色卡 WeaponDetail，魔之楔补齐到 slots 槽。"""
    padded = [*mods, *[None] * (slots - len(mods))][:slots]
    return WeaponDetail(
        attribute=WeaponAttribute(atk=0, crd=0.0, cri=0.0, speed=0.0, trigger=0.0),
        currentVolume=0,
        icon=_cdn_icon("Head", record["icon"]),
        id=record["id"],
        level=level,
        modes=[_mode(entry) for entry in padded],
        name=record["名称"],
        skillLevel=refine,
        sumVolume=0,
    )


def _weapon(engine: Engine, prefix: str) -> WeaponDetail | None:
    """近战 / 远程武器；没带或数据包未收录返回 None。"""
    weapon = engine.s[f"{prefix}Weapon"]
    if weapon["_isEmpty"]:
        return None
    record = records.weapon_record(weapon["id"])
    if record is None:
        return None
    mods = engine.s[f"{prefix}Mods"]
    return _weapon_detail(record, weapon["_等级"], weapon["_精炼"], mods, _WEAPON_MOD_SLOTS)


def _skill_weapon(engine: Engine, char_id: int) -> WeaponDetail | None:
    """同律武器：条目挂在角色下，角色没有同律武器返回 None。"""
    weapon = engine.s["skillWeapon"]
    record = records.con_weapon_record(char_id)
    # 继承型（芙罗拉/刻舟/煜明）没有图标和魔之楔，面板就是近战武器的，不单独画
    if weapon is None or record is None or "inherit" in record:
        return None
    mods = engine.s["skillMods"]
    return _weapon_detail(record, weapon["_等级"], weapon["_技能等级"], mods, _SKILL_WEAPON_MOD_SLOTS)


def _role(engine: Engine, char_id: int) -> RoleDetail:
    """按引擎装配结果合成角色卡用的 RoleDetail（基础四维取数据包按等级缩放值）。"""
    char = engine.s["char"]
    char_mods: list[dict | None] = list(engine.s["charMods"])
    char_mods += [None] * (len(_CHAR_SLOT_TO_MODE) - len(char_mods))
    modes = [_mode(char_mods[_CHAR_SLOT_TO_MODE.index(index)]) for index in range(len(_CHAR_SLOT_TO_MODE))]
    modes.append(_mode(engine.s["auraMod"]))
    # 引擎里的角色实例只留了计算字段，技能图标要回数据包原始条目取；能装配说明角色已收录
    skills = get_tables().char_by_id[char_id]["技能"]
    skill_icons = {skill["名称"]: skill["icon"] for skill in skills if "名称" in skill and skill.get("icon")}
    return RoleDetail(
        attribute=RoleAttribute.model_validate(
            {
                "atk": int(char["基础攻击"]),
                "maxHp": int(char["基础生命"]),
                "maxES": int(char["基础护盾"]),
                "def": int(char["基础防御"]),
                "maxSp": int(char["基础神智"]),
                "skillIntensity": "100%",
                "skillRange": "100%",
                "skillSustain": "100%",
                "skillEfficiency": "100%",
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
            for name, level in engine.skill_levels_final()
        ],
        paint="",
        charId=char_id,
        charName=char["名称"],
        elementIcon="",
        traces=[],
        currentVolume=0,
        sumVolume=0,
        level=char["_等级"],
        icon="",
        gradeLevel=0,
        elementName=char["属性"],
        modes=modes,
    )


async def synthesize_build(bdid: str) -> BuildCard | None:
    """线上构筑 → 角色卡数据；构筑不存在返回 None。"""
    info = (await _query(_BuildData, _BUILD_QUERY, {"id": bdid})).build
    if info is None:
        return None
    try:
        settings = json.loads(info.charSettings)
    except json.JSONDecodeError as error:
        raise DobFetchError(f"构筑 {bdid} 的设置无法解析：{error}") from error
    tables = get_tables()
    # 同 _recalc：用户上传的设置交给三方引擎，异常面无法枚举
    try:
        engine = Engine(build_state(info.charId, settings, tables), tables)
        target_value = engine.calculate()
    except KeyError as error:
        raise DobBuildError(f"含数据包未收录的条目 {error}") from error
    except Exception as error:
        raise DobBuildError(f"设置格式异常 {error!r}") from error
    candidates = (
        (WeaponSlot.MELEE, _weapon(engine, "melee")),
        (WeaponSlot.RANGED, _weapon(engine, "ranged")),
        (WeaponSlot.SKILL, _skill_weapon(engine, info.charId)),
    )
    weapons = {slot: weapon for slot, weapon in candidates if weapon is not None}
    return BuildCard(
        build=DobBuild(engine=engine, role=_role(engine, info.charId), weapons=weapons),
        bdid=info.id,
        title=info.title,
        author=info.user.name,
        author_qq=info.user.qq,
        target_fn=engine.s["targetFunction"],
        target_value=fmt_target_value(target_value),
        likes=info.likes,
        views=info.views,
    )
