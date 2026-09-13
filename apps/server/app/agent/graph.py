from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.context import AgentContext
from app.agent.nodes import finish, initialize, knowledge_search
from app.agent.state import AgentState


def create_agent_graph() -> CompiledStateGraph:
    """创建带独立内存 checkpoint 的最小 Agent Graph。"""

    builder = StateGraph(AgentState, context_schema=AgentContext)
    builder.add_node("initialize", initialize)
    builder.add_node("knowledge_search", knowledge_search)
    builder.add_node("finish", finish)
    builder.add_edge(START, "initialize")
    builder.add_edge("initialize", "knowledge_search")
    builder.add_edge("knowledge_search", "finish")
    builder.add_edge("finish", END)
    return builder.compile(checkpointer=InMemorySaver())


agent_graph = create_agent_graph()
