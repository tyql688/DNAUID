from __future__ import annotations

from contextlib import closing, contextmanager
from collections.abc import Iterator

from pydantic import BaseModel, JsonValue, TypeAdapter
from dna_builder_sdk.calc import WasmBackend, build_state
from dna_builder_sdk.calc.gamedata import GameDataTables


class DobBuildError(RuntimeError):
    """构筑装配或计算失败，调用方转为用户提示。"""


@contextmanager
def open_engine(char_id: int, settings: dict[str, JsonValue], tables: GameDataTables) -> Iterator[DobEngine]:
    """WASM 会话在同一线程内创建、结算并释放；外部数据错误转为用户提示。"""
    try:
        with closing(DobEngine(char_id, settings, tables)) as engine:
            yield engine
    except DobBuildError:
        raise
    except Exception as error:
        raise DobBuildError(str(error)) from error


class SkillField(BaseModel):
    name: str
    value: float
    value2: float | None = None
    format: str | None = None


class _Damage(BaseModel):
    expectedDamage: float


class _Evaluation(BaseModel):
    attributes: dict[str, float]
    targetValue: float
    targetFunction: str
    damage: _Damage | None
    error: str | None


class _SkillState(BaseModel):
    skillNames: list[str]
    skillLevelsFinal: list[int]


_PANELS = TypeAdapter(dict[str, dict[str, float]])
_FIELDS = TypeAdapter(list[SkillField])


class DobEngine:
    """同一 WASM 会话提供面板、技能字段、目标值与伤害乘区。"""

    def __init__(self, char_id: int, settings: dict[str, JsonValue], tables: GameDataTables) -> None:
        self.char_id = char_id
        self.settings = dict(settings)
        state = _SkillState.model_validate(build_state(char_id, settings, tables))
        self.skill_levels = list(zip(state.skillNames, state.skillLevelsFinal))
        # WASM 消费 settings 中的最终等级；build_state 只返回等级元数据。
        self.settings["charSkillLevel"] = [level for level in state.skillLevelsFinal[:3]]
        self._backend = WasmBackend(tables)

    def _evaluate(self, target: str | None = None) -> _Evaluation:
        result = _Evaluation.model_validate(self._backend.evaluate(self.char_id, self.settings, target))
        if result.error:
            raise DobBuildError(result.error)
        return result

    def calculate(self) -> tuple[str, float]:
        result = self._evaluate()
        return result.targetFunction, result.targetValue

    def char_panel(self) -> dict[str, float]:
        return self._evaluate("0").attributes

    def weapon_panels(self) -> dict[str, dict[str, float]]:
        return _PANELS.validate_python(self._backend.panels(self.char_id, self.settings))

    def damage_multiplier(self, slot: str) -> float:
        result = self._evaluate(f"[{slot}]")
        if result.damage is None:
            raise DobBuildError(f"{slot}武器缺少伤害结算结果")
        return result.damage.expectedDamage

    def skill_fields(self, name: str) -> list[SkillField]:
        return _FIELDS.validate_python(self._backend.skill_fields(self.char_id, self.settings, name))

    def close(self) -> None:
        self._backend.close()
