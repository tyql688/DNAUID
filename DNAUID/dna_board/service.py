"""DOB 榜单/构筑数据层：只走公开读接口与 dobsdk 快照，做取数与裁剪，不碰绘制。"""

from __future__ import annotations

import json
from datetime import datetime

from dna_builder_sdk import BackendClient, snapshot_from_online

from ..dna_sdk import datapack_store
from ..dna_sdk.build import SdkBuild
from ..dna_sdk.tables import mod_name, mod_record, char_record, weapon_record, mod_quality_int
from ..utils.api.model import Mode, RoleSkill, RoleDetail, WeaponDetail, RoleAttribute, WeaponAttribute
from ..utils.name_convert import id2name_data, char_name_to_char_id

# 角色构筑列表默认席数（克制密度：刚好够序号点选）
CHAR_BOARD_LIMIT = 10


def fmt_dps(value: float | int | None) -> str:
    """目标值格式化：7.4亿 / 3.2万，直观一位小数封顶。"""
    if value is None:
        return "--"
    num = float(value)
    if num >= 1e8:
        return f"{num / 1e8:.2f}亿"
    if num >= 1e4:
        return f"{num / 1e4:.1f}万"
    return f"{int(num)}"


def char_name(char_id: int | str | None) -> str:
    """bot 别名库 id→名，缺失时回退 ID 显示（不断整卡）。"""
    name = id2name_data.get(str(char_id)) if char_id is not None else None
    return name or f"ID:{char_id}"


def char_id_of(name: str) -> int | None:
    """角色名（含别名）→游戏 charId，找不到返回 None。"""
    found = char_name_to_char_id(name)
    try:
        return int(found) if found is not None else None
    except (TypeError, ValueError):
        return None


# 上游 RankingView 同款单查询：条目 + 构筑设置 + 作者一次拿全
_RANKING_QUERY = (
    "query($id:String!){rankingList(id:$id){id name desc items{id charId buildId sortOrder "
    "build{id title charId charSettings updateAt user{id name qq}}}}}"
)

# 缺图降级：CDN 直链补进同一缓存文件（与角色卡官方 URL 预热同一机制）。
# 规则与上游前端同构：T_Mod_/T_Skill_/T_Head_（见 LeveledMod/Skill/Weapon.url）。
CDN_BASE = "https://cdn.dna-builder.cn"  # 备援 https://cdn.dobapp.cc


def _cdn_url(path: str | None) -> str | None:
    return f"{CDN_BASE}/{path}" if path else None


def mod_icon_url(mod_id: int | str | None) -> str | None:
    """mod 图直链（T_Mod_），无记录/无 icon 返回 None（纯缓存）。"""
    try:
        record = mod_record(mod_id)
    except Exception:
        return None
    icon = record.get("icon") if record else None
    return _cdn_url(f"imgs/webp/T_Mod_{icon}.webp" if icon else None)


def weapon_icon_url(weapon_id: int | str | None) -> str | None:
    """武器图直链（T_Head_，与上游 LeveledWeapon.url 同构）。"""
    try:
        record = weapon_record(weapon_id)
    except Exception:
        return None
    icon = record.get("icon") if record else None
    return _cdn_url(f"imgs/webp/T_Head_{icon}.webp" if icon else None)


def skill_icon_map(char_id: int | str | None) -> dict[str, str]:
    """角色技能名→图直链（T_Skill_，仅读“技能”表；匹配不上的一律纯缓存）。"""
    try:
        record = char_record(char_id)
    except Exception:
        return {}
    out: dict[str, str] = {}
    entries = (record or {}).get("技能")
    if not isinstance(entries, list):
        return {}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("icon"):
            continue
        keys = [k for k in entry.keys() if k != "icon"]
        name = entry.get(keys[1]) if len(keys) > 1 else None
        if isinstance(name, str) and name:
            out[name] = _cdn_url(f"imgs/webp/T_Skill_{entry['icon']}.webp") or ""
    return {k: v for k, v in out.items() if v}


def head_icon_url(char_id: int | str | None) -> str | None:
    """角色头图直链（榜单行用，T_Head_）。"""
    try:
        record = char_record(char_id)
    except Exception:
        return None
    icon = record.get("icon") if record else None
    return _cdn_url(f"imgs/webp/T_Head_{icon}.webp" if icon else None)


# QQ 头像直链（作者栏，上游同款；QQ 号缺失时渲染层垫底）
QQ_AVATAR = "https://q1.qlogo.cn/g?b=qq&nk={qq}&s=100"


def qq_avatar_url(qq: str | int | None) -> str | None:
    """QQ 头像直链，无 qq 时返回 None（渲染层垫底）。"""
    try:
        qq_int = int(qq) if qq else 0
    except (TypeError, ValueError):
        return None
    return QQ_AVATAR.format(qq=qq_int) if qq_int > 0 else None


def _fmt_time(ms: int | None) -> str:
    if not ms:
        return "--"
    try:
        return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return "--"


def _recalc_row(item: dict, tables) -> dict:
    """单席重算：设置直读 baseName/targetFunction，Engine 本地重算 DPS（与上游一致）。"""
    from dna_builder_sdk.calc import Engine, build_state

    build = item.get("build") or {}
    char_id = build.get("charId") or item.get("charId")
    title = build.get("title") or build.get("id") or "(无标题)"
    user = build.get("user") or {}
    base_name, target_fn, dps = "-", "-", 0
    try:
        raw = build.get("charSettings")
        settings = json.loads(raw) if isinstance(raw, str) else (raw or {})
        base_name = settings.get("baseName") or "-"
        target_fn = settings.get("targetFunction") or "-"
        state = build_state(int(char_id), settings, tables)
        result = Engine(state, tables).calculate()
        dps = round(result) if result == result and result != float("inf") else 0
    except Exception:
        dps = 0
    return {
        "char_id": char_id,
        "char_name": datapack_name(char_id) or char_name(char_id),
        "head": head_icon_url(char_id),
        "title": title,
        "author": user.get("name") or "匿名",
        "author_qq": user.get("qq") or 0,
        "update_at": _fmt_time(build.get("updateAt")),
        "base_name": base_name,
        "target_fn": target_fn,
        "dps": dps,
        "dps_str": f"{dps:,}",
    }


def fetch_boards(client: BackendClient | None = None) -> list[dict]:
    """全部榜单：单查询拿全量，本地重算 DPS 后降序（与上游 RankingView 同口径）。"""
    client = client or BackendClient()
    tables = datapack_store().load_tables()
    boards: list[dict] = []
    for board in client.ranking_lists():
        data = client.graphql(_RANKING_QUERY, {"id": board["id"]})
        ranking = data.get("rankingList") or {}
        rows = [_recalc_row(item, tables) for item in ranking.get("items") or []]
        rows.sort(key=lambda r: r["dps"], reverse=True)
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
        boards.append({"name": ranking.get("name") or board.get("name") or "榜单", "rows": rows})
    return boards


# 角色构筑列表查询：builds 不带 user 关联时用自定义查询一次拿全（含作者）
_CHAR_BUILDS_QUERY = (
    "query($c:Int,$l:Int,$sb:String){builds(charId:$c,limit:$l,sortBy:$sb)"
    "{id title charId charSettings updateAt likes views user{id name qq}}}"
)


def fetch_char_builds(char_id: int, limit: int = CHAR_BOARD_LIMIT, client: BackendClient | None = None) -> list[dict]:
    """某角色构筑列表：按点赞排序，目标函数直读设置，DPS 本地重算（与榜单同口径）。"""
    from dna_builder_sdk.calc import Engine, build_state

    client = client or BackendClient()
    tables = datapack_store().load_tables()
    data = client.graphql(_CHAR_BUILDS_QUERY, {"c": int(char_id), "l": limit, "sb": "likes"})
    builds = (data.get("builds") or [])[:limit]
    rows: list[dict] = []
    for idx, build in enumerate(builds, start=1):
        user = build.get("user") or {}
        target_fn, dps = "-", 0
        try:
            raw = build.get("charSettings")
            settings = json.loads(raw) if isinstance(raw, str) else (raw or {})
            target_fn = settings.get("targetFunction") or "-"
            state = build_state(int(build.get("charId") or char_id), settings, tables)
            result = Engine(state, tables).calculate()
            dps = round(result) if result == result and result != float("inf") else 0
        except Exception:
            dps = 0
        rows.append(
            {
                "idx": idx,
                "bdid": build.get("id"),
                "char_id": build.get("charId") or char_id,
                "char_name": datapack_name(build.get("charId") or char_id) or char_name(char_id),
                "title": build.get("title") or "(无标题)",
                "author": user.get("name") or "匿名",
                "author_qq": user.get("qq") or 0,
                "update_at": _fmt_time(build.get("updateAt")),
                "likes": int(build.get("likes") or 0),
                "views": int(build.get("views") or 0),
                "target_fn": target_fn,
                "dps": dps,
                "dps_str": f"{dps:,}",
            }
        )
    return rows


def datapack_name(char_id: int | str | None) -> str | None:
    """数据包角色名（名称键），合成 RoleDetail 时优先用它，保证 entry 命中。"""
    try:
        record = char_record(char_id)
    except Exception:
        return None
    return record.get("名称") if record else None


def weapon_display_name(weapon_id: int | str | None) -> str:
    """数据包武器名，缺失回退 ID 显示。"""
    try:
        record = weapon_record(weapon_id)
    except Exception:
        record = None
    name = record.get("名称") if record else None
    return name or f"武器{weapon_id}"


def _bd_mode(pair) -> Mode:
    """BD 槽位 [id, level]（或裸 id/空）→ Mode；无图标无品质，渲染层回退数据包。"""
    if isinstance(pair, (list, tuple)):
        mod_id, level = (list(pair) + [0, 0])[:2]
    else:
        mod_id, level = pair, 0
    try:
        mod_id = int(mod_id) if mod_id else -1
    except (TypeError, ValueError):
        mod_id = -1
    if mod_id <= 0:
        return Mode(id=-1, level=0)
    return Mode(
        id=mod_id,
        level=int(level or 0),
        name=mod_name(mod_id),
        icon=mod_icon_url(mod_id),
        quality=mod_quality_int(mod_id),
    )


def _pad_modes(pairs: list, size: int = 8) -> list[Mode]:
    """槽位补齐到固定数（空槽 id=-1 画空框，与官方 modes 语义一致）。"""
    pairs = list(pairs or [])[:size]
    while len(pairs) < size:
        pairs.append(None)
    return [_bd_mode(p) for p in pairs]


# BD 8 角色槽 → modes[0..7] 映射（与官方 GAME_STYLE_MOD_SLOT_ORDER 同口径：
# 槽1=m0 槽2=m2 槽3=m3 槽4=m1 槽5=m6 槽6=m4 槽7=m7 槽8=m5）
CHAR_SLOT_TO_MODE = (0, 2, 3, 1, 6, 4, 7, 5)


def _datapack_base_main(char_id: int, level: int) -> dict[str, int]:
    """数据包基础四维（按实际等级缩放）：伤害段基础列用，与官方裸值同语义。"""
    from dna_builder_sdk.calc.entities import level_char

    try:
        entry = char_record(char_id)
        inst = level_char(entry, level) if entry else {}
    except Exception:
        return {}
    out: dict[str, int] = {}
    for display, key in (
        ("攻击", "基础攻击"),
        ("生命", "基础生命"),
        ("护盾", "基础护盾"),
        ("防御", "基础防御"),
        ("神智", "基础神智"),
    ):
        try:
            out[display] = int(inst.get(key) or 0)
        except (TypeError, ValueError):
            out[display] = 0
    return out


def synthesize_build(bdid: str, client: BackendClient | None = None) -> dict | None:
    """线上 BD → 角色卡管线直装：合成 RoleDetail/WeaponDetail + SdkBuild。

    Engine 直接复用快照装配好的那份（不再二次 build_state）；角色名/技能/mod/武器
    全部取 BD 自带值，图标走角色卡同一套缓存（缺图画空框，不断整卡）。
    查无此 BD 返回 None；数据包未就绪抛 SdkPackError（调用方转提示）。
    """
    client = client or BackendClient()
    build = client.build(bdid)
    if not build:
        return None
    try:
        detail = client.graphql("query($id:String!){build(id:$id){user{id name qq}}}", {"id": bdid})
        author = ((detail.get("build") or {}).get("user")) or {}
    except Exception:
        author = {}
    snap = snapshot_from_online(bdid, source=datapack_store(), backend=client)
    settings = snap.settings
    char_id = int(snap.char_id)
    name = datapack_name(char_id) or char_name(char_id)

    char_level = int(settings.get("charLevel") or 80)
    skill_icons = skill_icon_map(char_id)
    skills = [
        RoleSkill(skillId=0, icon=skill_icons.get(skill_name, ""), level=int(level), skillName=skill_name)
        for skill_name, level in snap.skill_levels_final()
    ]
    # 伤害段“基础→最终”列的基数：数据包按实际等级缩放的基础值（与官方裸值同语义）
    base_main = _datapack_base_main(char_id, char_level)
    char_mods = list(settings.get("charMods") or [])
    while len(char_mods) < 8:
        char_mods.append(None)
    modes: list[Mode | None] = [None] * 8
    for slot, pair in enumerate(char_mods[:8]):
        modes[CHAR_SLOT_TO_MODE[slot]] = _bd_mode(pair)
    modes.append(_bd_mode(settings.get("auraMod")))

    role = RoleDetail(
        attribute=RoleAttribute(
            **{
                "atk": base_main.get("攻击", 0),
                "maxHp": base_main.get("生命", 0),
                "maxES": base_main.get("护盾", 0),
                "def": base_main.get("防御", 0),
                "maxSp": base_main.get("神智", 0),
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
        skills=skills,
        paint="",
        charId=char_id,
        charName=name,
        elementIcon="",
        traces=[],
        currentVolume=0,
        sumVolume=0,
        level=char_level,
        icon="",
        gradeLevel=0,
        elementName="",
        modes=modes,
        conWeaponEid=None,
        conWeaponId=None,
    )

    def _weapon(prefix: str) -> WeaponDetail | None:
        wid = settings.get(f"{prefix}Weapon")
        if not wid:
            return None
        return WeaponDetail(
            attribute=WeaponAttribute(atk=0, crd=0.0, cri=0.0, speed=0.0, trigger=0.0),
            currentVolume=0,
            elementIcon=None,
            elementName=None,
            icon=weapon_icon_url(wid) or "",
            id=int(wid),
            level=int(settings.get(f"{prefix}WeaponLevel") or 1),
            modes=_pad_modes(settings.get(f"{prefix}Mods")),
            name=weapon_display_name(wid),
            skillLevel=int(settings.get(f"{prefix}WeaponRefine") or 1),
            sumVolume=0,
        )

    weapons = {"close": _weapon("melee"), "ranged": _weapon("ranged")}
    sdk_build = SdkBuild(engine=snap.engine, role=role, weapons=weapons, missing_mods=[])
    summary = snap.summary()
    return {
        "build": sdk_build,
        "bdid": bdid,
        "title": summary.get("title") or build.get("title") or "(无标题)",
        "char_name": name,
        "char_level": char_level,
        "author": author.get("name") or "匿名",
        "author_qq": author.get("qq") or 0,
        "dps": fmt_dps(summary.get("targetValue")),
        "target_fn": summary.get("target") or "",
        "likes": int(build.get("likes") or 0),
        "views": int(build.get("views") or 0),
    }
