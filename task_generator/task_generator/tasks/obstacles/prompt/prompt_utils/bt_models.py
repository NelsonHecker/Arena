from __future__ import annotations

import xml.etree.ElementTree as ET
from abc import ABC
import typing

from pydantic import BaseModel, Field, field_validator

CONTROL_NODE_ID_MAP = {}

DECORATION_NODE_ID_MAP = {
    "TimeDelayDecorator": "TimeDelay"
}

ACTION_NODE_ID_MAP = {
    "GroupWalk": "SetGroupWalk",
}

CONDITION_NODE_ID_MAP = {}


# TreeNodesModel
# --------------
class InputPort(BaseModel):
    name: str
    type: str
    default: typing.Optional[str] = None
    description: typing.Optional[str] = None

    def to_xml(self) -> ET.Element:
        element = ET.Element(
            "input_port",
            attrib={
                "name": self.name,
                "type": self.type
            }
        )
        if self.default:
            element.set("default", self.default)
        if self.description:
            element.text = self.description

        return element


class OutputPort(BaseModel):
    name: str
    type: str
    default: typing.Optional[str] = None
    description: typing.Optional[str] = None

    def to_xml(self) -> ET.Element:
        element = ET.Element(
            "output_port",
            attrib={
                "name": self.name,
                "type": self.type
            }
        )
        if self.default:
            element.set("default", self.default)
        if self.description:
            element.text = self.description

        return element


class Condition(BaseModel):
    ID: str
    input_ports: typing.Optional[list[InputPort]] = []
    output_port: typing.Optional[list[OutputPort]] = []

    def to_xml(self) -> ET.Element:
        element = ET.Element(
            "Condition",
            attrib={
                "ID": self.ID
            }
        )

        for ip in self.input_ports or []:
            ip: InputPort
            element.append(ip.to_xml())

        for op in self.output_port or []:
            op: OutputPort
            element.append(op.to_xml())

        return element


class Action(BaseModel):
    ID: str
    input_ports: typing.Optional[list[InputPort]] = []
    output_port: typing.Optional[list[OutputPort]] = []

    @field_validator("ID")
    @classmethod
    def normalize_id(cls, v):
        if v in ACTION_NODE_ID_MAP:
            return ACTION_NODE_ID_MAP[v]
        return v

    def to_xml(self) -> ET.Element:
        element = ET.Element(
            "Action",
            attrib={
                "ID": self.ID
            }
        )

        for ip in self.input_ports or []:
            ip: InputPort
            element.append(ip.to_xml())

        for op in self.output_port or []:
            op: OutputPort
            element.append(op.to_xml())

        return element


class TreeNodesModel(BaseModel):
    conditions: typing.Optional[list[Condition]] = []
    actions: typing.Optional[list[Action]] = []

    def to_xml(self) -> ET.Element:
        element = ET.Element(
            "TreeNodesModel",
            attrib={}
        )

        for action in self.actions or ():
            element.append(action.to_xml())

        for condition in self.conditions or ():
            element.append(condition.to_xml())

        return element

# BehaviorTree
# ------------


class TreeNode(BaseModel):
    ID: typing.Any
    name: str
    attributes: dict[str, typing.Any] = {}

    def to_xml(self) -> ET.Element:
        ...


class DecorationNode(TreeNode):
    ID: typing.Literal[
        "TimeDelayDecorator",
        "RetryUntilSuccessful"
    ]
    child_node: NodeUnion

    @field_validator("ID")
    @classmethod
    def normalize_id(cls, v):
        if v in DECORATION_NODE_ID_MAP:
            return DECORATION_NODE_ID_MAP[v]
        return v

    def to_xml(self):
        element = ET.Element(
            self.ID,
            attrib=self.attributes
        )

        element.append(self.child_node.to_xml())

        return element


class ControlNode(TreeNode):
    ID: typing.Literal[
        "Sequence",
        "Fallback"
    ]
    children_nodes: list[NodeUnion]

    def to_xml(self):
        element = ET.Element(
            self.ID,
            attrib=self.attributes
        )

        for node in self.children_nodes:
            element.append(node.to_xml())

        return element


class LeafNode(ABC, TreeNode):
    def to_xml(self):
        element = ET.Element(
            self.ID,
            attrib=self.attributes
        )

        return element


class ActionNode(LeafNode):
    ID: typing.Literal[
        # Old nodes
        "UpdateGoal",
        "RegularNav",
        "SurprisedNav",
        "CuriousNav",
        "ScaredNav",
        "ThreateningNav",
        # New nodes
        "FindNearestAgent",
        "SaySomething",
        "SetGroupId",
        "SetGoal",
        "StopMovement",
        "ResumeMovement",
        "StopAndWaitTimerAction",
        "ConversationFormation",
        "GoTo",
        "ApproachAgent",
        "ApproachRobot",
        "BlockRobot",
        "BlockAgent",
        "GroupWalk",
        "LookAtPoint",
        "LookAtAgent",
        "LookAtRobot",
        "FollowAgent",
    ]

    @field_validator("ID")
    @classmethod
    def normalize_id(cls, v):
        if v in ACTION_NODE_ID_MAP:
            return ACTION_NODE_ID_MAP[v]
        return v


class ConditionNode(LeafNode):
    ID: typing.Literal[
        # Old nodes
        "IsGoalReached",
        "IsRobotVisible",
        # New nodes
        "RandomChanceCondition",
        "IsRobotFacingAgent",
        "IsAgentVisible",
        "IsRobotClose",
        "IsAgentClose",
        "IsAtPosition",
        "IsAnyoneSpeaking",
        "IsSpeaking",
        "IsAnyoneLookingAtMe",
        "IsLookingAtMe"
    ]


class BehaviorTree(BaseModel):
    ID: str
    child_node: NodeUnion

    def to_xml(self) -> ET.Element:
        element = ET.Element(
            "BehaviorTree",
            attrib={
                "ID": self.ID
            }
        )

        element.append(self.child_node.to_xml())

        return element


class Root(BaseModel):
    main_tree_to_execute: str
    BTCPP_format: str
    tree_nodes_model: TreeNodesModel
    behavior_trees: list[BehaviorTree]

    def to_xml(
        self,
        include_ros_pkg: str = "arena_simulation_setup",
        include_path: str = "configs/hunav/behavior_trees/BTRegularNav.xml"
    ) -> ET.Element:
        element = ET.Element(
            "root",
            attrib={
                "main_tree_to_execute": self.main_tree_to_execute,
                "BTCPP_format": self.BTCPP_format
            }
        )

        element.append(self.tree_nodes_model.to_xml())

        element.append(
            ET.Element(
                "include",
                attrib={
                    "ros_pkg": include_ros_pkg,
                    "path": include_path
                }
            )
        )

        for behavior_tree in self.behavior_trees:
            element.append(behavior_tree.to_xml())

        return element


NodeUnion = typing.Annotated[
    typing.Union[ControlNode, DecorationNode, ActionNode, ConditionNode],
    Field(discriminator="ID")
]

if __name__ == "__main__":
    from xml.dom import minidom

    from .context import behavior_tree_format, strip_behavior_tree_format

    json_str = strip_behavior_tree_format(behavior_tree_format)

    test = Root.model_validate_json(json_str)

    xml_str = test.to_xml()
    pretty_bytes = minidom.parseString(
        ET.tostring(xml_str, encoding="UTF-8")
    ).toprettyxml(indent="  ", encoding="UTF-8")

    pretty_str = pretty_bytes.decode("UTF-8")
    print(pretty_str)
