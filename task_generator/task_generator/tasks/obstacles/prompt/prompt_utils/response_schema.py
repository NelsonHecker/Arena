from typing import Any, List, Literal, Tuple, Dict, TypeVar
from pydantic import BaseModel, Field

from .const import (
    AgentModel,
    GenerationMode,
    EmegencySingleAgentNodeName,
    EmergencyMultiAgentNodeName,
    CustomSingleAgentNodeName,
    CustomMultiAgentNodeName,
    NormalSingleAgentNodeName,
    NormalMultiAgentNodeName,
    QueuingSingleAgentNodeName,
    QueuingMultiAgentNodeName,
)

GenerationModeTypeVar = TypeVar("GenerationModeTypeVar", bound=GenerationMode)


class _SingleAgentNodeBase(BaseModel):
    attributes: Dict[str, Any] = Field(description="Parameters passed to the node")
    order: int = Field(
        description=(
            "Execution order in the agent behavior tree. "
            "Must be unique across all nodes for that agent."
        )
    )


class _MultiAgentNodeBase(BaseModel):
    attributes: Dict[str, Any] = Field(description="Parameters passed to the node")
    orders: Dict[str, int] = Field(
        description=(
            "Mapping: <agent_name> -> execution order in that agent’s tree. "
            "Order values must be unique per agent."
        )
    )


class EmergencySingleAgentNode(_SingleAgentNodeBase):
    name: EmegencySingleAgentNodeName = Field(
        description="Name of the node, only use provided node name, do not modify!"
    )


class EmergencyMultiAgentNode(_MultiAgentNodeBase):
    name: EmergencyMultiAgentNodeName = Field(
        description="Name of the node, only use provided node name, do not modify!"
    )


class CustomSingleAgentNode(_SingleAgentNodeBase):
    name: CustomSingleAgentNodeName = Field(
        description="Name of the node, only use provided node name, do not modify!"
    )


class CustomMultiAgentNode(_MultiAgentNodeBase):
    name: CustomMultiAgentNodeName = Field(
        description="Name of the node, only use provided node name, do not modify!"
    )


class NormalSingleAgentNode(_SingleAgentNodeBase):
    name: NormalSingleAgentNodeName = Field(
        description="Name of the node, only use provided node name, do not modify!"
    )


class NormalMultiAgentNode(_MultiAgentNodeBase):
    name: NormalMultiAgentNodeName = Field(
        description="Name of the node, only use provided node name, do not modify!"
    )


class QueuingSingleAgentNode(_SingleAgentNodeBase):
    name: QueuingSingleAgentNodeName = Field(
        description="Name of the node, only use provided node name, do not modify!"
    )


class QueuingMultiAgentNode(_MultiAgentNodeBase):
    name: QueuingMultiAgentNodeName = Field(
        description="Name of the node, only use provided node name, do not modify!"
    )


class Agent(BaseModel):
    name: str = Field(description='The agent\'s unique identifier (e.g., "hunav_1")')
    pos: Tuple[float, float, float] = Field(
        description="A tuple (x, y, yaw) representing the object's position and rotation. You should pay attention to where the agent should be spawned and faced, place the agent within the correct zone and adjust the yaw reasonably."
    )
    type: Literal["adult", "child"] = Field(description="The type of the agent.")
    model: AgentModel = Field(description="The model of the agent")


class CustomResponseSchema(BaseModel):
    hunav_agents: List[Agent] = Field(description="Contains a list of hunav agents")
    single_agent_nodes: List[CustomSingleAgentNode] = Field(
        description="Contains a list of behavior tree nodes that one and only one agent involved in"
    )
    multi_agent_nodes: List[CustomMultiAgentNodeName] = Field(
        description="Contains a list of behavior tree nodes that more than one agent involved in"
    )


class EmergencyResponseSchema(BaseModel):
    hunav_agents: List[Agent] = Field(description="Contains a list of hunav agents")
    single_agent_nodes: List[EmergencySingleAgentNode] = Field(
        description="Contains a list of behavior tree nodes that one and only one agent involved in"
    )
    multi_agent_nodes: List[EmergencyMultiAgentNode] = Field(
        description="Contains a list of behavior tree nodes that more than one agent involved in"
    )


class NormalResponseSchema(BaseModel):
    hunav_agents: List[Agent] = Field(description="Contains a list of hunav agents")
    single_agent_nodes: List[NormalSingleAgentNode] = Field(
        description="Contains a list of behavior tree nodes that one and only one agent involved in"
    )
    multi_agent_nodes: List[NormalMultiAgentNodeName] = Field(
        description="Contains a list of behavior tree nodes that more than one agent involved in"
    )


class QueuingResponseSchema(BaseModel):
    hunav_agents: List[Agent] = Field(description="Contains a list of hunav agents")
    single_agent_nodes: List[QueuingSingleAgentNode] = Field(
        description="Contains a list of behavior tree nodes that one and only one agent involved in"
    )
    multi_agent_nodes: List[QueuingMultiAgentNode] = Field(
        description="Contains a list of behavior tree nodes that more than one agent involved in"
    )
