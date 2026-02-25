from typing import Literal
from enum import Enum


class GenerationMode(Enum):
    EMERGENCY = "emergency"
    CUSTOM = "custom"
    NORMAL = "normal"
    QUEUING = "queuing"
    AUTO = "auto"

    @classmethod
    def has_value(cls, value):
        return value in cls._value2member_map_


AgentModel = Literal[
    "female_adult_business_02",
    "female_adult_medical_01",
    "female_adult_police_01",
    "female_adult_police_02",
    "female_adult_police_03",
    "male_adult_construction_01",
    "male_adult_construction_02",
    "male_adult_construction_03",
    "male_adult_construction_05",
    "male_adult_medical_01",
    "male_adult_police_04",
]


AllSingleAgentNodeName = Literal[
    "ApproachAgent",
    "BlockAgent",
    "FindNearestAgent",
    "FollowAgent",
    "FollowVelocityField",
    "GoTo",
    "IsAgentClose",
    "IsAgentVisible",
    "IsAnyoneLookingAtMe",
    "IsAnyoneSpeaking",
    "IsAtPosition",
    "IsLookingAtMe",
    "IsSpeaking",
    "LookAtAgent",
    "LookAtPoint",
    "RandomChanceCondition",
    "ResumeMovement",
    "SaySomething",
    "StopAndWaitTimerAction",
    "StopMovement",
]

EmergencySingleAgentNodeName = Literal["FollowVelocityField"]  # GoTo could be in here
CustomSingleAgentNodeName = AllSingleAgentNodeName
NormalSingleAgentNodeName = Literal[
    "ApproachAgent",
    "BlockAgent",
    "FindNearestAgent",
    "FollowAgent",
    "GoTo",
    "IsAgentClose",
    "IsAgentVisible",
    "IsAnyoneLookingAtMe",
    "IsAnyoneSpeaking",
    "IsAtPosition",
    "IsLookingAtMe",
    "IsSpeaking",
    "LookAtAgent",
    "LookAtPoint",
    "RandomChanceCondition",
    "ResumeMovement",
    "SaySomething",
    "StopAndWaitTimerAction",
    "StopMovement",
]
QueuingSingleAgentNodeName = Literal["GoTo"]


AllMultiAgentNodeType = Literal[
    "AdvanceQueue",
    "ConversationFormation",
    "FormQueue",
    "GroupWalk",
]

EmergencyMultiAgentNodeName = Literal[""]  # GroupWalk could be in here
CustomMultiAgentNodeName = AllMultiAgentNodeType
NormalMultiAgentNodeName = Literal["ConversationFormation", "GroupWalk"]
QueuingMultiAgentNodeName = Literal["AdvanceQueue", "FormQueue"]
