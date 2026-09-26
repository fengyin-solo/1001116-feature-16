"""闸口通行业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "gate"
REQUIRED_FIELDS = ["通行编号", "车牌号码", "关联箱号"]
WATCH_FIELDS = ["车牌号码", "关联箱号"]
STATUS_ORDER = ["待放行", "已放行", "已拦截", "已复核"]
ACTION_RULES = {"确认放行": "已放行", "拦截车辆": "已拦截", "复核通行": "已复核"}
NEGATIVE_ACTIONS = ["拦截车辆"]
DISPLAY_STATUS_FIELD = "通行状态"
REVIEW_ACTION = "复核通行"
REVIEW_COUNT_FIELD = "复核次数"


def missing_fields(entry: dict[str, Any]) -> list[str]:
    """车牌号码、关联箱号任一缺失都要单独挑出，按字段值实时算，不依赖缓存标记。"""
    return [field for field in WATCH_FIELDS if not str(entry.get(field) or "").strip()]


class GateService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        plate: str | None = None,
        container: str | None = None,
        status: str | None = None,
        incomplete: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("通行编号", ""))]
        if plate:
            rows = [row for row in rows if plate in str(row.get("车牌号码", ""))]
        if container:
            rows = [row for row in rows if container in str(row.get("关联箱号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if incomplete:
            rows = [row for row in rows if missing_fields(row)]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._present(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry[DISPLAY_STATUS_FIELD] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry[REVIEW_COUNT_FIELD] = 0
        rows.append(entry)
        return self._present(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"通行记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于闸口通行可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        if action == REVIEW_ACTION and entry.get("status") == ACTION_RULES[REVIEW_ACTION]:
            # 同一张通行记录重复复核只算一次：状态与复核次数都保持原样
            return self._present(entry), "该通行记录已复核，本次不重复计入"
        entry["status"] = target
        # 列表、详情、道口看板读的是同一条记录，显示字段与内部状态一起落库，刷新后口径不变
        entry[DISPLAY_STATUS_FIELD] = target
        entry["pending"] = target == STATUS_ORDER[0]
        if action in NEGATIVE_ACTIONS:
            entry["abnormal"] = True
        elif target == "已放行":
            entry["abnormal"] = False
        if action == REVIEW_ACTION:
            entry[REVIEW_COUNT_FIELD] = int(entry.get(REVIEW_COUNT_FIELD, 0)) + 1
        return self._present(entry), f"通行记录已{action}"

    def summary(self) -> list[dict[str, Any]]:
        """道口看板口径：与列表同源统计，动作落库后即同步。"""
        rows = store.rows(MODULE)
        return [
            {"label": "今日进闸车次", "value": sum(1 for row in rows if "进" in str(row.get("进出方向", "")))},
            {"label": "今日出闸车次", "value": sum(1 for row in rows if "出" in str(row.get("进出方向", "")))},
            {"label": "待放行", "value": sum(1 for row in rows if row.get("status") == STATUS_ORDER[0])},
            {"label": "拦截车次", "value": sum(1 for row in rows if row.get("status") == "已拦截")},
            {"label": "资料缺失", "value": sum(1 for row in rows if missing_fields(row))},
        ]

    @staticmethod
    def _present(row: dict[str, Any]) -> dict[str, Any]:
        """补出缺失字段标记，列表与详情走同一份展示口径，不改库里的原始记录。"""
        missing = missing_fields(row)
        presented = dict(row)
        presented["资料缺失"] = bool(missing)
        presented["缺失字段"] = "、".join(missing)
        return presented
