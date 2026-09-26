"""闸口通行业务规则：状态流转、字段校验与筛选口径都收在这里。

读写口径约定：
- ``status`` 是唯一可信的通行状态，展示用的「通行状态」字段在读取时由它投影出来，
  任何动作之后都不再允许两处状态各写各的；
- 「确认放行 / 拦截车辆 / 复核通行」三类道口值守动作照旧；
- 复核是终态且幂等：同一条通行记录重复复核只算一次；
- 车牌号码或关联箱号缺失的记录用 ``incomplete`` 口径单独挑出。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "gate"
REQUIRED_FIELDS = ["通行编号", "车牌号码", "关联箱号"]
DETAIL_FIELDS = ["进出方向", "通行时间", "道口编号", "值守人员"]
PENDING = "待放行"
RELEASED = "已放行"
BLOCKED = "已拦截"
REVIEWED = "已复核"
STATUS_ORDER = [PENDING, RELEASED, BLOCKED, REVIEWED]
ACTION_RULES = {"确认放行": RELEASED, "拦截车辆": BLOCKED, "复核通行": REVIEWED}


class GateService:
    # ---- 读取 -----------------------------------------------------------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        incomplete: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self._present(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("通行编号", ""))]
        if status:
            rows = [row for row in rows if row["status"] == status]
        if incomplete:
            rows = [row for row in rows if row["incomplete"]]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._present(entry) if entry is not None else None

    def stats(self) -> dict[str, int]:
        """道口看板用的汇总数字，与列表同一份数据，避免两处口径漂移。"""
        rows = [self._present(row) for row in store.rows(MODULE)]
        today = datetime.now().strftime("%Y-%m-%d")
        return {
            "待放行": sum(1 for row in rows if row["status"] == PENDING),
            "已放行": sum(1 for row in rows if row["status"] == RELEASED),
            "已拦截": sum(1 for row in rows if row["status"] == BLOCKED),
            "已复核": sum(1 for row in rows if row["status"] == REVIEWED),
            "今日进闸": sum(
                1 for row in rows
                if str(row.get("进出方向", "")).strip() == "进闸"
                and str(row.get("通行时间", "")).startswith(today)
            ),
            "今日出闸": sum(
                1 for row in rows
                if str(row.get("进出方向", "")).strip() == "出闸"
                and str(row.get("通行时间", "")).startswith(today)
            ),
            "信息缺失": sum(1 for row in rows if row["incomplete"]),
        }

    def board(self) -> list[dict[str, Any]]:
        """道口看板：按道口编号分组，列出每个道口的最新记录与状态计数。"""
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in store.rows(MODULE):
            entry = self._present(row)
            key = str(entry.get("道口编号") or "未分配道口")
            groups.setdefault(key, []).append(entry)

        result: list[dict[str, Any]] = []
        for gate_no, entries in sorted(groups.items()):
            entries.sort(key=lambda item: str(item.get("通行时间") or ""), reverse=True)
            result.append({
                "道口编号": gate_no,
                "待放行": sum(1 for item in entries if item["status"] == PENDING),
                "已放行": sum(1 for item in entries if item["status"] == RELEASED),
                "已拦截": sum(1 for item in entries if item["status"] == BLOCKED),
                "已复核": sum(1 for item in entries if item["status"] == REVIEWED),
                "值守人员": next(
                    (str(item.get("值守人员", "")).strip() for item in entries
                     if str(item.get("值守人员", "")).strip()),
                    "",
                ),
                "最近通行": entries[0],
                "records": entries,
            })
        return result

    # ---- 写入 -----------------------------------------------------------
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry.update({field: values.get(field) for field in DETAIL_FIELDS})
        entry["status"] = PENDING
        entry["pending"] = True
        entry["abnormal"] = False
        entry["reviewed"] = False
        entry["复核时间"] = ""
        rows.append(entry)
        return self._present(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"通行记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于闸口通行可执行范围"
        target = ACTION_RULES[action]

        # 复核终态幂等：已经复核过的记录重复点「复核通行」只提示，不再改任何数据。
        if action == "复核通行" and (entry.get("reviewed") or entry.get("status") == REVIEWED):
            return self._present(entry), "该通行记录已复核，重复复核只计一次"

        entry["status"] = target
        # pending / abnormal 同步落库，运营概览直接读原始行也能拿到一致口径。
        entry["pending"] = target == PENDING
        entry["abnormal"] = target == BLOCKED
        if action == "复核通行":
            entry["reviewed"] = True
            entry["复核时间"] = datetime_now()
        elif action in ("确认放行", "拦截车辆"):
            # 放行或拦截视为新一轮处置，之前的复核痕迹清空，后续仍可再复核。
            entry["reviewed"] = False
            entry["复核时间"] = ""
        return self._present(entry), f"通行记录已{action}"

    # ---- 统一投影 -------------------------------------------------------
    def _present(self, row: dict[str, Any]) -> dict[str, Any]:
        """以 ``status`` 为唯一状态口径输出记录，列表、详情、看板都走这一份。"""
        item = dict(row)
        status = str(item.get("status") or PENDING)
        if status not in STATUS_ORDER:
            status = PENDING
        item["status"] = status
        # 展示字段始终跟随 status，避免刷新前后、列表与详情两处看到不同结果。
        item["通行状态"] = status
        item["pending"] = status == PENDING
        item["abnormal"] = status == BLOCKED
        item["reviewed"] = bool(item.get("reviewed")) or status == REVIEWED
        item.setdefault("复核时间", "")
        missing_fields = [
            field for field in ("车牌号码", "关联箱号")
            if not str(item.get(field) or "").strip()
        ]
        item["incomplete"] = bool(missing_fields)
        item["missing_fields"] = missing_fields
        return item


def datetime_now() -> str:
    """取当前时间字符串；单独留函数方便以后换成统一时钟。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M")
