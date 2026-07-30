from __future__ import annotations

import re
from dataclasses import dataclass

from ..utils import dna_api
from ..utils.api.model import Mode, RoleDetail, WeaponDetail
from ..utils.database.models import DNAUser
from ..utils.api.damage_model import (
    DEFAULT_ENEMY_CONFIG_ID,
    ModeSelection,
    RestraintType,
    SkillSelection,
    BuildConfigData,
    BuildConfigType,
    CharacterCalculateData,
    WeaponCalculateRequest,
    CharacterCalculateRequest,
)
from ..utils.api.request_util import DNAApiResp

_SKILL_LEVEL_BONUS_RE = re.compile(
    r"\[([^\]]+)]\s*等级\s*\+\s*(\d+)",
)
# 角色 Lv.30 虽在官网下拉中，但计算接口会返回 500。
_OFFICIAL_CHARACTER_LEVELS = frozenset((1, 20, 40, 50, 60, 70, 80))
_OFFICIAL_WEAPON_LEVELS = frozenset((1, 20, 30, 40, 50, 60, 70, 80))


@dataclass(frozen=True, slots=True, kw_only=True)
class DamageCompanion:
    name: str
    environment_config_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        name = self.name.strip()
        if name == "":
            raise ValueError("协战同伴名称不能为空")
        if any(config_id <= 0 for config_id in self.environment_config_ids):
            raise ValueError(f"协战同伴 {name} 的环境配置 ID 必须为正整数")
        if len(set(self.environment_config_ids)) != len(self.environment_config_ids):
            raise ValueError(f"协战同伴 {name} 的环境配置 ID 不能重复")
        object.__setattr__(self, "name", name)


@dataclass(frozen=True, slots=True, kw_only=True)
class RoleDamageBuild:
    role_detail: RoleDetail
    con_weapon_detail: WeaponDetail | None = None
    close_weapon_detail: WeaponDetail | None = None
    lang_range_weapon_detail: WeaponDetail | None = None
    companions: tuple[DamageCompanion, ...] = ()
    environment_config_ids: tuple[int, ...] = ()
    is_sv: bool = False
    is_ev: bool = False
    restraint_type: RestraintType = RestraintType.NONE
    enemy_config_id: int = DEFAULT_ENEMY_CONFIG_ID

    def __post_init__(self) -> None:
        if len(self.companions) > 2:
            raise ValueError("伤害方案最多支持两名协战同伴")
        all_environment_ids = self.all_environment_config_ids
        if any(config_id <= 0 for config_id in all_environment_ids):
            raise ValueError("环境配置 ID 必须为正整数")
        if len(set(all_environment_ids)) != len(all_environment_ids):
            raise ValueError("伤害方案中的环境配置 ID 不能重复")
        if self.enemy_config_id <= 0:
            raise ValueError("敌人配置 ID 必须为正整数")

    @property
    def all_environment_config_ids(self) -> tuple[int, ...]:
        companion_ids = tuple(
            config_id for companion in self.companions for config_id in companion.environment_config_ids
        )
        return self.environment_config_ids + companion_ids


def _build_mode_selections(modes: list[Mode]) -> list[ModeSelection]:
    selections: list[ModeSelection] = []
    for mode in modes:
        if mode.id <= 0:
            continue
        if mode.level is None:
            raise ValueError(f"魔之楔 {mode.id} 缺少等级")
        selections.append(ModeSelection(id=mode.id, level=mode.level))
    return selections


def _build_weapon_request(
    weapon_detail: WeaponDetail,
) -> WeaponCalculateRequest:
    return WeaponCalculateRequest(
        weaponId=weapon_detail.id,
        weaponModes=_build_mode_selections(weapon_detail.modes),
        skillLevel=weapon_detail.skillLevel,
        weaponLevel=weapon_detail.level,
    )


def get_skill_extend_level(
    skill_level: int,
    max_extend_level: int,
) -> int:
    if skill_level >= 8:
        return min(2, max_extend_level)
    if skill_level >= 4:
        return min(1, max_extend_level)
    return 0


def _get_official_skills(
    config: BuildConfigData,
    char_id: int,
) -> dict[int, int] | None:
    for item in config.build_config:
        if item.type != BuildConfigType.ROLE or item.third_id != char_id:
            continue
        if item.skill_ids is None or item.skill_ids == "":
            return {}
        skill_ids = tuple(int(skill_id) for skill_id in item.skill_ids.split(","))
        break
    else:
        return None

    extend_limits = dict.fromkeys(skill_ids, 0)
    for item in config.build_config:
        if item.type not in (
            BuildConfigType.SKILL,
            BuildConfigType.SKILL_EXTRA_EFFECT,
        ):
            continue
        parent_skill_id = item.parent_skill_id
        if parent_skill_id not in extend_limits:
            continue
        extend_limits[parent_skill_id] += 1
    return {skill_id: min(extend_limit, 2) for skill_id, extend_limit in extend_limits.items()}


def get_calculation_skill_levels(
    role_detail: RoleDetail,
    skill_ids: tuple[int, ...],
) -> dict[int, int]:
    bonuses: dict[str, int] = {}
    for trace in role_detail.traces[: role_detail.gradeLevel]:
        for skill_name, bonus_text in _SKILL_LEVEL_BONUS_RE.findall(
            trace.description,
        ):
            bonus = int(bonus_text)
            if skill_name in bonuses:
                bonuses[skill_name] += bonus
            else:
                bonuses[skill_name] = bonus

    skills = {skill.skillId: skill for skill in role_detail.skills}
    levels: dict[int, int] = {}
    for skill_id in skill_ids:
        if skill_id not in skills:
            raise ValueError(
                f"角色 {role_detail.charName} 缺少官方技能 {skill_id}",
            )
        skill = skills[skill_id]
        grade_bonus = bonuses[skill.skillName] if skill.skillName in bonuses else 0
        level = skill.level - grade_bonus
        if level < 1:
            raise ValueError(
                f"角色「{role_detail.charName}」的技能「{skill.skillName}」等级与官网配置不一致",
            )
        levels[skill_id] = level
    return levels


def build_role_damage_request(
    build: RoleDamageBuild,
    official_skills: dict[int, int],
) -> CharacterCalculateRequest:
    role_detail = build.role_detail
    skill_levels = get_calculation_skill_levels(
        role_detail,
        tuple(official_skills),
    )
    con_weapon_detail = build.con_weapon_detail
    con_weapon_modes = [] if con_weapon_detail is None else _build_mode_selections(con_weapon_detail.modes)
    return CharacterCalculateRequest(
        charGradeLevel=role_detail.gradeLevel,
        charLevel=role_detail.level,
        charModes=_build_mode_selections(role_detail.modes),
        charSkills=[
            SkillSelection(
                extendLevel=get_skill_extend_level(
                    level,
                    official_skills[skill_id],
                ),
                id=str(skill_id),
                level=level,
            )
            for skill_id, level in skill_levels.items()
        ],
        conWeaponModes=con_weapon_modes,
        charId=role_detail.charId,
        closeWeapon=(None if build.close_weapon_detail is None else _build_weapon_request(build.close_weapon_detail)),
        langRangeWeapon=(
            None if build.lang_range_weapon_detail is None else _build_weapon_request(build.lang_range_weapon_detail)
        ),
        isSv=build.is_sv,
        isEv=build.is_ev,
        environmentConfigIds=list(build.all_environment_config_ids),
        restraintType=build.restraint_type,
        enemyConfigId=build.enemy_config_id,
    )


async def calculate_role_damage(
    dna_user: DNAUser,
    build: RoleDamageBuild,
) -> DNAApiResp[CharacterCalculateData]:
    role_detail = build.role_detail
    config_response = await dna_api.get_damage_config(dna_user)
    if not config_response.is_success:
        return DNAApiResp[CharacterCalculateData].err(config_response.msg)
    if config_response.data is None:
        raise RuntimeError("官方 H5 配置响应缺少 data")

    official_skills = _get_official_skills(
        config_response.data,
        role_detail.charId,
    )
    if official_skills is None:
        return DNAApiResp[CharacterCalculateData].err(
            f"官方 H5 缺少{role_detail.charName}的伤害配置",
        )
    if not official_skills:
        return DNAApiResp[CharacterCalculateData].err(
            f"官方 H5 暂未开放{role_detail.charName}的伤害计算",
        )

    if role_detail.level not in _OFFICIAL_CHARACTER_LEVELS:
        return DNAApiResp[CharacterCalculateData].err(
            f"角色「{role_detail.charName}」Lv.{role_detail.level} 不在官网计算档位中",
        )

    weapons = (
        ("近战武器", build.close_weapon_detail),
        ("远程武器", build.lang_range_weapon_detail),
    )
    for label, weapon in weapons:
        if weapon is not None and weapon.level not in _OFFICIAL_WEAPON_LEVELS:
            return DNAApiResp[CharacterCalculateData].err(
                f"{label}「{weapon.name}」Lv.{weapon.level} 不在官网计算档位中",
            )

    try:
        request = build_role_damage_request(build, official_skills)
    except ValueError as error:
        return DNAApiResp[CharacterCalculateData].err(str(error))
    return await dna_api.calculate_damage(dna_user, request)
