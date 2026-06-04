import json

from ..utils.name_convert import (
    all_char_list,
    all_weapon_list,
    alias_to_char_name,
    builtin_alias_list,
    alias_to_weapon_name,
    alias_to_char_name_list,
    alias_to_weapon_name_list,
)
from ..utils.resource.RESOURCE_PATH import CHAR_ALIAS_PATH, WEAPON_ALIAS_PATH


async def action_char_alias(action: str, char_name: str, new_alias: str) -> str:
    if not CHAR_ALIAS_PATH.exists():
        return "别名配置文件不存在，请检查文件路径"

    with open(CHAR_ALIAS_PATH, "r", encoding="UTF-8") as f:
        data = json.load(f)

    std_char_name = alias_to_char_name(char_name)
    if not std_char_name:
        return f"角色【{char_name}】不存在，请检查名称"

    if action == "添加":
        check_new_alias = alias_to_char_name(new_alias)
        if check_new_alias:
            return f"别名【{new_alias}】已被角色【{check_new_alias}】占用"

        # 角色可能只存在于内置层，data 文件还没有对应 key
        data.setdefault(std_char_name, []).append(new_alias)
        with open(CHAR_ALIAS_PATH, "w", encoding="UTF-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return f"成功为角色【{char_name}】添加别名【{new_alias}】"

    elif action == "删除":
        if new_alias in data.get(std_char_name, []):
            data[std_char_name].remove(new_alias)
            with open(CHAR_ALIAS_PATH, "w", encoding="UTF-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return f"成功为角色【{std_char_name}】删除别名【{new_alias}】"

        if new_alias in builtin_alias_list(std_char_name):
            return f"别名【{new_alias}】为内置别名，无法删除"
        return f"别名【{new_alias}】不存在，无法删除"

    return "无效的操作，请检查操作"


async def char_alias_list(char_name: str) -> str:
    std_char_name = alias_to_char_name(char_name)
    if not std_char_name:
        return f"角色【{char_name}】不存在，请检查名称"

    alias_list = alias_to_char_name_list(char_name)
    if not alias_list:
        return f"角色【{char_name}】不存在，请检查名称"

    return f"角色【{char_name}】别名列表：\n" + "\n".join(alias_list)


async def all_char_list_alias() -> str:
    char_list = all_char_list()
    return "角色列表：\n" + "\n".join(char_list)


async def action_weapon_alias(action: str, weapon_name: str, new_alias: str) -> str:
    if not WEAPON_ALIAS_PATH.exists():
        return "武器别名配置文件不存在"

    with open(WEAPON_ALIAS_PATH, "r", encoding="UTF-8") as f:
        data = json.load(f)

    std_weapon_name = alias_to_weapon_name(weapon_name)
    # alias_to_weapon_name 查不到时原样返回输入，用合并视图判断武器是否存在
    if not alias_to_weapon_name_list(std_weapon_name):
        return f"武器【{weapon_name}】不存在，请检查名称"

    if action == "添加":
        if alias_to_weapon_name_list(new_alias):
            return f"别名【{new_alias}】已被武器【{alias_to_weapon_name(new_alias)}】占用"

        # 武器可能只存在于内置层，data 文件还没有对应 key
        data.setdefault(std_weapon_name, []).append(new_alias)
        with open(WEAPON_ALIAS_PATH, "w", encoding="UTF-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return f"成功为武器【{weapon_name}】添加别名【{new_alias}】"

    elif action == "删除":
        if new_alias in data.get(std_weapon_name, []):
            data[std_weapon_name].remove(new_alias)
            with open(WEAPON_ALIAS_PATH, "w", encoding="UTF-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return f"成功为武器【{std_weapon_name}】删除别名【{new_alias}】"

        if new_alias in builtin_alias_list(std_weapon_name, is_weapon=True):
            return f"别名【{new_alias}】为内置别名，无法删除"
        return f"别名【{new_alias}】不存在，无法删除"

    return "无效的操作，请检查操作"


async def weapon_alias_list(weapon_name: str) -> str:
    std_weapon_name = alias_to_weapon_name(weapon_name)
    if not std_weapon_name:
        return f"武器【{weapon_name}】不存在，请检查名称"

    alias_list = alias_to_weapon_name_list(weapon_name)
    if not alias_list:
        return f"武器【{weapon_name}】不存在，请检查名称"

    return f"武器【{std_weapon_name}】别名列表：\n" + "\n".join(alias_list)


async def all_weapon_list_alias() -> str:
    weapon_list = all_weapon_list()
    return "武器列表：\n" + "\n".join(weapon_list)
