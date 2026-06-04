import json
from typing import Any, Dict, List, Optional
from pathlib import Path

from ..utils.api.model import RoleShowForTool
from ..utils.resource.RESOURCE_PATH import (
    ID2NAME_PATH,
    CHAR_ALIAS_PATH,
    WEAPON_ALIAS_PATH,
)

# 别名分三层：
# 1. 内置别名：随插件发布（进 git），位于 dna_alias/alias/，只读
# 2. 自动别名：游戏接口重建，写 data 目录（CHAR_ALIAS_PATH / WEAPON_ALIAS_PATH）
# 3. 自定义别名：添加别名命令写入，与自动别名同文件
# 运行时合并为一个视图，所有查询走合并后的 char_alias_data / weapon_alias_data
BUILTIN_ALIAS_PATH = Path(__file__).parent.parent / "dna_alias" / "alias"
BUILTIN_CHAR_ALIAS_PATH = BUILTIN_ALIAS_PATH / "char_alias.json"
BUILTIN_WEAPON_ALIAS_PATH = BUILTIN_ALIAS_PATH / "weapon_alias.json"

# 内置层（只读）
builtin_char_alias_data: Dict[str, List[str]] = {}
builtin_weapon_alias_data: Dict[str, List[str]] = {}
# 合并视图（内置 + 自动 + 自定义）
char_alias_data: Dict[str, List[str]] = {}
weapon_alias_data: Dict[str, List[str]] = {}
id2name_data: Dict[str, str] = {}


def _read_alias_data(alias_path: Path, ensure_file: bool = False) -> Dict[str, Any]:
    try:
        data = json.loads(alias_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        if ensure_file:
            alias_path.write_text("{}", encoding="utf-8")
        return {}


def _merge_alias_data(builtin: Dict[str, List[str]], extra: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """内置层在前，data 层（自动+自定义）去重追加"""
    merged = {name: list(aliases) for name, aliases in builtin.items()}
    for name, aliases in extra.items():
        base = merged.setdefault(name, [])
        base.extend(a for a in aliases if a not in base)
    return merged


def _fill_auto_alias(metadatas: List[Dict[str, Any]], alias_data: Dict[str, List[str]]) -> None:
    for meta in metadatas:
        name = meta["name"]
        if name not in alias_data or len(alias_data[name]) == 0:
            alias_data[name] = [name]


async def rebuild_name_convert(role_show: RoleShowForTool, is_force: bool = False):
    """用游戏接口的角色/武器列表重建自动别名层（只写 data 目录，不动内置层）"""
    char_alias = {} if is_force else _read_alias_data(CHAR_ALIAS_PATH)
    weapon_alias = {} if is_force else _read_alias_data(WEAPON_ALIAS_PATH)

    role_metadatas = [{"name": i.name, "id": i.charId} for i in role_show.roleChars]
    weapon_metadatas = [{"name": i.name, "id": i.weaponId} for i in role_show.langRangeWeapons + role_show.closeWeapons]
    _fill_auto_alias(role_metadatas, char_alias)
    _fill_auto_alias(weapon_metadatas, weapon_alias)
    id2name = {str(i["id"]): i["name"] for i in role_metadatas + weapon_metadatas}

    with open(CHAR_ALIAS_PATH, "w", encoding="utf-8") as f:
        json.dump(char_alias, f, ensure_ascii=False, indent=2)
    with open(WEAPON_ALIAS_PATH, "w", encoding="utf-8") as f:
        json.dump(weapon_alias, f, ensure_ascii=False, indent=2)
    with open(ID2NAME_PATH, "w", encoding="utf-8") as f:
        json.dump(id2name, f, ensure_ascii=False, indent=2)

    load_alias_data()


async def refresh_name_convert(is_force: bool = False):
    from ..utils import dna_api
    from ..utils.api.model import DNARoleForToolRes
    from ..utils.name_convert import rebuild_name_convert

    dna_user = await dna_api.get_random_dna_user()
    if not dna_user:
        return False, "没有可用的DNA用户"
    role_show = await dna_api.get_default_role_for_tool(dna_user.cookie, dna_user.dev_code)
    if not role_show.is_success:
        return False, "获取角色列表信息失败"
    role_show = DNARoleForToolRes.model_validate(role_show.data)
    await rebuild_name_convert(role_show.roleInfo.roleShow, is_force=is_force)
    return True, "别名恢复成功"


def load_alias_data():
    global builtin_char_alias_data, builtin_weapon_alias_data
    global char_alias_data, weapon_alias_data, id2name_data

    builtin_char_alias_data = _read_alias_data(BUILTIN_CHAR_ALIAS_PATH)
    builtin_weapon_alias_data = _read_alias_data(BUILTIN_WEAPON_ALIAS_PATH)
    char_alias_data = _merge_alias_data(builtin_char_alias_data, _read_alias_data(CHAR_ALIAS_PATH, ensure_file=True))
    weapon_alias_data = _merge_alias_data(
        builtin_weapon_alias_data, _read_alias_data(WEAPON_ALIAS_PATH, ensure_file=True)
    )
    id2name_data = _read_alias_data(ID2NAME_PATH, ensure_file=True)


load_alias_data()


def builtin_alias_list(std_name: str, is_weapon: bool = False) -> List[str]:
    """指定正名的内置别名列表（正名需已通过 alias_to_*_name 解析）"""
    data = builtin_weapon_alias_data if is_weapon else builtin_char_alias_data
    return data.get(std_name, [])


def alias_to_char_name(char_name: Optional[str]) -> Optional[str]:
    if not char_name:
        return None
    for i in char_alias_data:
        if (char_name in i) or (char_name in char_alias_data[i]):
            return i
    return None


def alias_to_char_name_list(char_name: str) -> List[str]:
    for i in char_alias_data:
        if (char_name in i) or (char_name in char_alias_data[i]):
            return char_alias_data[i]
    return []


def char_name_to_char_id(char_name: Optional[str]) -> Optional[str]:
    char_name = alias_to_char_name(char_name)
    for _id, _name in id2name_data.items():
        if _name == char_name:
            return _id
    return None


def alias_to_weapon_name(weapon_name: str) -> str:
    for i in weapon_alias_data:
        if (weapon_name in i) or (weapon_name in weapon_alias_data[i]):
            return i

    if "专武" in weapon_name:
        char_name = weapon_name.replace("专武", "")
        name = alias_to_char_name(char_name)
        weapon_name = f"{name}专武"

    for i in weapon_alias_data:
        if (weapon_name in i) or (weapon_name in weapon_alias_data[i]):
            return i

    return weapon_name


def alias_to_weapon_name_list(weapon_name: str) -> List[str]:
    for i in weapon_alias_data:
        if (weapon_name in i) or (weapon_name in weapon_alias_data[i]):
            return weapon_alias_data[i]
    return []


def all_weapon_list() -> List[str]:
    return list(weapon_alias_data.keys())


def all_char_list() -> List[str]:
    return list(char_alias_data.keys())
