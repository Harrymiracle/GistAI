from dataclasses import dataclass, field
from typing import Mapping

from app.agent.schemas import AgentAction, EvidenceStatus


@dataclass(frozen=True, slots=True)
class AgentLimits:
    """单次 Agent Run 的集中式固定预算。"""

    max_kb_searches: int = 2
    max_rewrites: int = 1
    max_web_searches: int = 1
    max_article_reads: int = 2
    max_web_page_reads: int = 2
    max_steps: int = 8


@dataclass(frozen=True, slots=True)
class PolicyOutcome:
    """Policy 对当前状态给出的合法动作与终止结论。"""

    allowed_actions: list[AgentAction]
    should_terminate: bool = False
    termination_action: AgentAction | None = None
    reason: str | None = None

@dataclass(frozen=True, slots=True)
class AgentRuntimePolicy:
    """只依据状态和固定预算计算边界，不调用任何外部依赖。"""

    limits: AgentLimits = field(default_factory=AgentLimits)

    def evaluate(self, state: Mapping[str, object]) -> PolicyOutcome:
        if self._must_stop_progress(state):
            return self._terminal_options(state)

        actions: list[AgentAction] = []
        if self._has_answer_candidate(state) and self._freshness_verified(state):
            actions.append(AgentAction.ANSWER)
        if self._count(state, "rewrite_count") < self.limits.max_rewrites:
            actions.append(AgentAction.REWRITE_QUERY)
        if (
            bool(state.get("allow_web"))
            and self.tool_calls(state, "web_search") < self.limits.max_web_searches
        ):
            actions.append(AgentAction.WEB_SEARCH)
        if self._has_unread_article(state):
            actions.append(AgentAction.GET_ARTICLE_CONTENT)
        if self._has_unfetched_web_page(state):
            actions.append(AgentAction.FETCH_WEB_PAGE)

        if not actions:
            return self.terminate(state, "没有剩余的合法动作。")

        actions.append(AgentAction.INSUFFICIENT)
        return PolicyOutcome(allowed_actions=actions)

    def can_execute(
        self,
        state: Mapping[str, object],
        action: AgentAction,
    ) -> bool:
        """为 Node 提供不依赖 LLM 的最后一道预算校验。"""

        if self._must_stop_progress(state):
            return False
        if action is AgentAction.KNOWLEDGE_SEARCH:
            return (
                self.tool_calls(state, "knowledge_search")
                < self.limits.max_kb_searches
            )
        if action is AgentAction.REWRITE_QUERY:
            return self._count(state, "rewrite_count") < self.limits.max_rewrites
        if action is AgentAction.WEB_SEARCH:
            return bool(state.get("allow_web")) and (
                self.tool_calls(state, "web_search")
                < self.limits.max_web_searches
            )
        if action is AgentAction.GET_ARTICLE_CONTENT:
            return self._has_unread_article(state)
        if action is AgentAction.FETCH_WEB_PAGE:
            return self._has_unfetched_web_page(state)
        return action in self.evaluate(state).allowed_actions

    def should_force_web_for_freshness(
        self,
        state: Mapping[str, object],
    ) -> bool:
        """时效性问题在首次决策前必须先尝试一次 Web Search。"""

        return (
            bool(state.get("requires_freshness"))
            and bool(state.get("allow_web"))
            and not self._freshness_verified(state)
            and self.tool_calls(state, "web_search")
            < self.limits.max_web_searches
            and not self._must_stop_progress(state)
        )

    def terminate(
        self,
        state: Mapping[str, object],
        reason: str,
    ) -> PolicyOutcome:
        """根据已选可靠证据决定 Partial 或 Insufficient。"""

        if state.get("selected_evidence"):
            status = state.get("evidence_status")
            action = (
                AgentAction.ANSWER
                if status is EvidenceStatus.SUFFICIENT
                else AgentAction.PARTIAL_ANSWER
            )
        else:
            action = AgentAction.INSUFFICIENT
        return PolicyOutcome(
            allowed_actions=[],
            should_terminate=True,
            termination_action=action,
            reason=reason,
        )

    def tool_calls(self, state: Mapping[str, object], tool_name: str) -> int:
        counts = state.get("tool_call_counts")
        if not isinstance(counts, Mapping):
            return 0
        value = counts.get(tool_name, 0)
        return value if isinstance(value, int) else 0

    def _must_stop_progress(self, state: Mapping[str, object]) -> bool:
        return (
            self._count(state, "step_count") >= self.limits.max_steps
            or state.get("last_error_type") is not None
        )

    def _terminal_options(self, state: Mapping[str, object]) -> PolicyOutcome:
        if self._has_answer_candidate(state) and self._freshness_verified(state):
            return PolicyOutcome(
                allowed_actions=[AgentAction.ANSWER, AgentAction.INSUFFICIENT]
            )
        return self.terminate(state, "运行预算已耗尽或发生不可恢复错误。")

    def _has_answer_candidate(self, state: Mapping[str, object]) -> bool:
        return any(
            bool(state.get(key))
            for key in (
                "kb_results",
                "web_results",
                "article_fulltext_evidence",
                "web_fulltext_evidence",
            )
        )

    def _freshness_verified(self, state: Mapping[str, object]) -> bool:
        return not bool(state.get("requires_freshness")) or bool(
            state.get("web_results") or state.get("web_fulltext_evidence")
        )

    def _has_unread_article(self, state: Mapping[str, object]) -> bool:
        if (
            self.tool_calls(state, "get_article_content")
            >= self.limits.max_article_reads
        ):
            return False
        read_ids = set(state.get("read_article_ids") or [])
        return any(
            item.get("article_id") is not None
            and item.get("article_id") not in read_ids
            for item in state.get("kb_results") or []
        )

    def _has_unfetched_web_page(self, state: Mapping[str, object]) -> bool:
        if (
            self.tool_calls(state, "fetch_web_page")
            >= self.limits.max_web_page_reads
        ):
            return False
        fetched_urls = set(state.get("fetched_web_urls") or [])
        return any(
            item.get("url") is not None
            and str(item.get("url")) not in fetched_urls
            for item in state.get("web_results") or []
        )

    @staticmethod
    def _count(state: Mapping[str, object], key: str) -> int:
        value = state.get(key, 0)
        return value if isinstance(value, int) else 0
