from __future__ import annotations

from dataclasses import dataclass

from ..utils import dna_api
from ..utils.api.model import Mode, RoleDetail, WeaponDetail
from ..utils.database.models import DNAUser
from ..utils.api.damage_model import (
    DEFAULT_ENEMY_CONFIG_ID,
    ModeSelection,
    RestraintType,
    SkillSelection,
    CharacterCalculateData,
    WeaponCalculateRequest,
    CharacterCalculateRequest,
)
from ..utils.api.request_util import DNAApiResp

_SKILL_GRADE_BONUSES = (
    ((3, 2),),
    ((5, 2),),
    ((3, 1), (5, 1)),
)


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


def get_skill_extend_level(skill_level: int) -> int:
    if skill_level >= 8:
        return 2
    if skill_level >= 4:
        return 1
    return 0


def get_calculation_skill_levels(
    role_detail: RoleDetail,
) -> dict[int, int]:
    if len(role_detail.skills) != len(_SKILL_GRADE_BONUSES):
        raise ValueError(f"角色 {role_detail.charName} 的主技能数量必须为 3，实际为 {len(role_detail.skills)}")

    levels: dict[int, int] = {}
    for skill, grade_bonuses in zip(
        role_detail.skills,
        _SKILL_GRADE_BONUSES,
        strict=True,
    ):
        grade_bonus = sum(bonus for required_grade, bonus in grade_bonuses if role_detail.gradeLevel >= required_grade)
        level = skill.level - grade_bonus
        if level < 1:
            raise ValueError(f"角色 {role_detail.charName} 的技能 {skill.skillName} 扣除溯源加成后等级为 {level}")
        levels[skill.skillId] = level
    return levels


def build_role_damage_request(
    build: RoleDamageBuild,
) -> CharacterCalculateRequest:
    role_detail = build.role_detail
    skill_levels = get_calculation_skill_levels(role_detail)
    con_weapon_detail = build.con_weapon_detail
    con_weapon_modes = [] if con_weapon_detail is None else _build_mode_selections(con_weapon_detail.modes)
    return CharacterCalculateRequest(
        charGradeLevel=role_detail.gradeLevel,
        charLevel=role_detail.level,
        charModes=_build_mode_selections(role_detail.modes),
        charSkills=[
            SkillSelection(
                extendLevel=get_skill_extend_level(skill_levels[skill.skillId]),
                id=str(skill.skillId),
                level=skill_levels[skill.skillId],
            )
            for skill in role_detail.skills
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
    # 构造请求体阶段可能因角色数据不满足伤害计算前置条件而抛 ValueError
    # （例如艾达有 4 个主技能，与固定 3 档加成表不匹配）。
    # 此处捕获并降级为失败响应，使伤害段显示错误提示，
    # 而非让异常冒泡导致整个角色面板命令崩溃。
    try:
        request = build_role_damage_request(build)
    except ValueError as exc:
        return DNAApiResp[CharacterCalculateData].err(str(exc))
    return await dna_api.calculate_damage(dna_user, request)
