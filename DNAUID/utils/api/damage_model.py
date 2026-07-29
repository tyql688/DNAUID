from __future__ import annotations

from enum import IntEnum
from typing import ClassVar

from pydantic import Field, BaseModel, ConfigDict


class _DamageModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
        extra="ignore",
    )


class BuildConfigType(IntEnum):
    ROLE = 1
    WEAPON = 2
    SKILL = 4
    WEDGE = 5
    ATTRIBUTE = 6
    SKILL_EXTRA_EFFECT = 11
    ENEMY = 13


class WedgePosition(IntEnum):
    ROLE = 1
    ROLE_MIDDLE = 2
    CO_MELEE_WEAPON = 3
    CO_RANGED_WEAPON = 4
    MELEE_WEAPON = 5
    RANGED_WEAPON = 6


class RestraintType(IntEnum):
    UNRESTRAINED = 0
    NONE = 1
    RESTRAINED = 2


DEFAULT_ENEMY_CONFIG_ID = 59


class ModeSelection(_DamageModel):
    id: int = Field(description="魔之楔配置 thirdId")
    level: int = Field(description="魔之楔等级")


class SkillSelection(_DamageModel):
    extend_level: int = Field(alias="extendLevel", description="技能突破等级")
    id: str = Field(description="技能配置 thirdId")
    level: int = Field(description="技能等级")


class WeaponCalculateRequest(_DamageModel):
    weapon_id: int = Field(alias="weaponId", description="武器配置 thirdId")
    weapon_modes: list[ModeSelection] = Field(
        default_factory=list,
        alias="weaponModes",
        description="武器魔之楔",
    )
    skill_level: int = Field(alias="skillLevel", description="武器精炼等级")
    weapon_level: int = Field(alias="weaponLevel", description="武器等级")


class CharacterCalculateRequest(_DamageModel):
    char_grade_level: int = Field(alias="charGradeLevel", description="角色溯源等级")
    char_level: int = Field(alias="charLevel", description="角色等级")
    char_modes: list[ModeSelection] = Field(
        default_factory=list,
        alias="charModes",
        description="角色魔之楔",
    )
    char_skills: list[SkillSelection] = Field(
        default_factory=list,
        alias="charSkills",
        description="角色技能",
    )
    con_weapon_modes: list[ModeSelection] = Field(
        default_factory=list,
        alias="conWeaponModes",
        description="同律武器魔之楔",
    )
    char_id: int = Field(alias="charId", description="角色配置 thirdId")
    close_weapon: WeaponCalculateRequest | None = Field(
        default=None,
        alias="closeWeapon",
        description="近战武器",
    )
    lang_range_weapon: WeaponCalculateRequest | None = Field(
        default=None,
        alias="langRangeWeapon",
        description="远程武器，字段名沿用网页协议",
    )
    is_sv: bool = Field(alias="isSv", description="是否启用昂扬")
    is_ev: bool = Field(alias="isEv", description="是否启用背水")
    environment_config_ids: list[int] = Field(
        default_factory=list,
        alias="environmentConfigIds",
        description="协战与环境增益配置 ID",
    )
    restraint_type: RestraintType = Field(
        default=RestraintType.NONE,
        alias="restraintType",
        description="克制关系，默认无克制",
    )
    enemy_config_id: int = Field(
        default=DEFAULT_ENEMY_CONFIG_ID,
        alias="enemyConfigId",
        description="敌人配置 ID，默认剧目-无尽第 31 轮",
    )


class EnvironmentCalculateRequest(_DamageModel):
    environment_config_ids: list[int] = Field(
        alias="environmentConfigIds",
        description="环境增益配置 ID",
    )


class BuildConfigItem(_DamageModel):
    id: int = Field(description="服务端配置主键")
    third_id: int = Field(alias="thirdId", description="游戏配置 ID")
    type: int = Field(description="配置类型")
    name: str = Field(description="名称")
    extend: str | None = Field(default=None, description="扩展配置 JSON 字符串")
    icon: str | None = Field(default=None, description="图标地址")
    paint: str | None = Field(default=None, description="立绘地址")
    skill_ids: str | None = Field(
        default=None,
        alias="skillIds",
        description="关联技能 ID",
    )
    create_time: int = Field(alias="createTime", description="创建时间毫秒")
    update_time: int = Field(alias="updateTime", description="更新时间毫秒")
    con_weapon_id: int | None = Field(
        default=None,
        alias="conWeaponId",
        description="同律武器 ID",
    )
    element: int | None = Field(default=None, description="元素类型")
    quality: int | None = Field(default=None, description="品质")
    weapon_type: int | None = Field(
        default=None,
        alias="weaponType",
        description="武器类型",
    )
    parent_skill_id: int | None = Field(
        default=None,
        alias="parentSkillId",
        description="父技能 ID",
    )
    mode_pre_type: int | None = Field(
        default=None,
        alias="modePreType",
        description="魔之楔前置类型",
    )
    position_type: int | None = Field(
        default=None,
        alias="positionType",
        description="魔之楔位置",
    )


class ModeConfigItem(_DamageModel):
    third_id: int = Field(alias="thirdId", description="魔之楔配置 ID")
    type: int = Field(description="配置类型")
    level: int = Field(description="等级")
    mode_total: int | None = Field(
        default=None,
        alias="modeTotal",
        description="总耐受值",
    )
    cos_mode: int | None = Field(
        default=None,
        alias="cosMode",
        description="当前等级耐受值",
    )


class EnemyConfigItem(_DamageModel):
    id: int = Field(description="敌人配置 ID")
    dungeon_name: str = Field(alias="dungeonName", description="副本名称")
    dungeon_level: int | None = Field(
        default=None,
        alias="dungeonLevel",
        description="副本等级",
    )
    round_num: int = Field(alias="roundNum", description="轮次")
    enemy_level: int = Field(alias="enemyLevel", description="敌人等级")
    create_time: int = Field(alias="createTime", description="创建时间毫秒")
    update_time: int = Field(alias="updateTime", description="更新时间毫秒")


class EnvironmentConfigItem(_DamageModel):
    id: int = Field(description="环境配置 ID")
    third_id: int = Field(alias="thirdId", description="来源角色或配置 ID")
    type: int = Field(description="配置类型")
    level: int = Field(description="等级")
    is_default: int | None = Field(
        default=None,
        alias="isDefault",
        description="是否默认生效",
    )
    description: str = Field(description="效果描述")


class BuildConfigData(_DamageModel):
    build_config: list[BuildConfigItem] = Field(
        alias="buildConfig",
        description="角色、武器、技能与魔之楔配置",
    )
    modes_config: list[ModeConfigItem] = Field(
        alias="modesConfig",
        description="魔之楔等级与耐受配置",
    )
    enemy_attribute_config: list[EnemyConfigItem] = Field(
        alias="enemyAttributeConfig",
        description="敌人配置",
    )
    environment_attribute_config: list[EnvironmentConfigItem] = Field(
        alias="environmentAttributeConfig",
        description="协战与环境增益配置",
    )


class AttributeBag(_DamageModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        populate_by_name=True,
        extra="allow",
    )

    empty: bool | None = Field(default=None, description="属性集合是否为空")
    atk: float | None = Field(default=None, description="攻击")
    atk1: float | None = Field(default=None, description="环境攻击加成")
    def_: float | None = Field(default=None, alias="def", description="防御")
    hp: float | None = Field(default=None, description="生命")
    es: float | None = Field(default=None, description="护盾")
    sp: float | None = Field(default=None, description="最大神志或武器属性")
    se: float | None = Field(default=None, description="技能效益")
    si: float | None = Field(default=None, description="技能威力")
    sr: float | None = Field(default=None, description="技能范围")
    ss: float | None = Field(default=None, description="技能耐久")
    sv: float | None = Field(default=None, description="昂扬")
    ev: float | None = Field(default=None, description="背水")
    cri: float | None = Field(default=None, description="暴击")
    crd: float | None = Field(default=None, description="暴击伤害")
    tr: float | None = Field(default=None, description="触发概率")


class SkillAttribute(_DamageModel):
    key: str = Field(description="属性名称")
    value: str | int | float | None = Field(default=None, description="基础值")
    environment_value: str | int | float | None = Field(
        default=None,
        alias="environmentValue",
        description="应用环境后的值",
    )


class SkillResult(_DamageModel):
    id: int = Field(description="技能 ID")
    name: str = Field(description="技能名称")
    parent_id: int | None = Field(
        default=None,
        alias="parentId",
        description="父技能 ID，派生技能据此归入主技能",
    )
    normal_skill_attributes: list[SkillAttribute] = Field(
        default_factory=list,
        alias="normalSkillAttributes",
        description="普通技能属性",
    )
    damage_skill_attributes: list[SkillAttribute] = Field(
        default_factory=list,
        alias="damageSkillAttributes",
        description="伤害属性",
    )


class DamageResult(_DamageModel):
    close_weapon_damage: str | None = Field(
        default=None,
        alias="closeWeaponDamage",
        description="近战伤害",
    )
    con_weapon_damage: str | None = Field(
        default=None,
        alias="conWeaponDamage",
        description="同律武器伤害",
    )
    lang_range_weapon_damage: str | None = Field(
        default=None,
        alias="langRangeWeaponDamage",
        description="远程伤害",
    )
    close_weapon_damage_with_environment: str | None = Field(
        default=None,
        alias="closeWeaponDamageWithEnvironment",
        description="应用环境后的近战伤害",
    )
    con_weapon_damage_with_environment: str | None = Field(
        default=None,
        alias="conWeaponDamageWithEnvironment",
        description="应用环境后的同律武器伤害",
    )
    lang_range_weapon_damage_with_environment: str | None = Field(
        default=None,
        alias="langRangeWeaponDamageWithEnvironment",
        description="应用环境后的远程伤害",
    )


class CharacterCalculateData(_DamageModel):
    skills: list[SkillResult] = Field(description="技能结果")
    damage: DamageResult = Field(description="三类武器伤害")
    final_attribute: AttributeBag = Field(
        alias="finalAttribute",
        description="最终角色属性",
    )
    base_attribute: AttributeBag = Field(
        alias="baseAttribute",
        description="基础角色属性",
    )


class WeaponCalculateData(_DamageModel):
    base_weapon_attribute: AttributeBag = Field(
        alias="baseWeaponAttribute",
        description="基础武器属性",
    )
    final_weapon_attribute: AttributeBag = Field(
        alias="finalWeaponAttribute",
        description="最终武器属性",
    )


class EnvironmentCalculateData(_DamageModel):
    environment: AttributeBag = Field(description="汇总环境属性")
