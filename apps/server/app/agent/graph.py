from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.nodes import finish, initialize
from app.agent.state import AgentState


def create_agent_graph() -> CompiledStateGraph:
    """创建带独立内存 checkpoint 的最小 Agent Graph。"""

    builder = StateGraph(AgentState)
    builder.add_node("initialize", initialize)
    builder.add_node("finish", finish)
    builder.add_edge(START, "initialize")
    builder.add_edge("initialize", "finish")
    builder.add_edge("finish", END)
    return builder.compile(checkpointer=InMemorySaver())


agent_graph = create_agent_graph()
