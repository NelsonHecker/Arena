import json
import os
import pickle
import tempfile
import time
from typing import Dict, List, Literal, get_args
import xml.etree.ElementTree as ET

# Avoids errors related to cv2 + pyglet + X11 with arena_text_crowd
os.environ["PYGLET_HEADLESS"] = "true"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import attrs
from pydantic import TypeAdapter

import numpy as np

from google import genai

from std_msgs.msg import Float32MultiArray, MultiArrayDimension
from ament_index_python.packages import get_package_share_directory

import pyglet

pyglet.options["headless"] = True

from arena_hunav_sim_bridge.agent.llm_parser import Parser

from arena_text_crowd.crowd_generation_pipeline.arena_text_crowd_generation_pipeline import (
    ArenaTextCrowdGenerationPipelineConfig as ATCPConfig,
    CrowdGenerationPipeline,
)
from arena_text_crowd.crowd_generation_pipeline.velocity_field_generation.velocity_field_generation_pipeline import (
    VelocityFieldGenerationPipelineConfig as VFGPConfig,
)
from arena_text_crowd.converters.arena_world_to_text_crowd_scenario import (
    arena_world_to_text_crowd_scenario,
)

from arena_rclpy_mixins.ROSParamServer import ROSParamT

from arena_simulation_setup.tree.World import WorldDescription, WorldIdentifier
from arena_simulation_setup.utils.cattrs import converter

from hunav_msgs.srv import SetVelocityField, SetArenaWorldBounds

# from task_generator.simulators.human.hunav.hunav import HunavDynamicObstacle
from task_generator.tasks.obstacles import (
    DynamicObstacle,
    Obstacle,
    TM_Obstacles,
)
from task_generator.tasks.obstacles.prompt.velocity_field_marker import (
    VelocityFieldVisualizer,
)
from arena_hunav_sim_bridge.global_planner.waypoints_visualizer import (
    WaypointVisualizer,
)
from arena_text_crowd.crowd_generation_pipeline.velocity_field_generation.arena_velocity_field_generation_pipeline import (
    ArenaVelocityFieldGenerationPipelineConfig,
    ArenaVelocityFieldGenerationPipeline,
)

from .prompt_utils import (
    GenerationMode,
    SYSTEM_INSTRUCTION,
    EMERGENCY_MODE,
    CUSTOM_MODE,
    NORMAL_MODE,
    QUEUING_MODE,
    SPLIT_PROMPT_INSTRUCTION,
    BT_REF_DOC_PATH,
    CHROMA_DB_PATH,
    LOCAL_LM,
    REMOTE_FAST_LM,
    REMOTE_REASONING_LM,
    create_chroma_db,
    get_chroma_collection,
    get_relevant_bt_nodes,
    process_json_doc,
    get_world_detail_info,
    get_world_metatdata,
    CustomResponseSchema,
    EmergencyResponseSchema,
    NormalResponseSchema,
    QueuingResponseSchema,
    EmergencySingleAgentNodeName,
    EmergencyMultiAgentNodeName,
    CustomSingleAgentNodeName,
    CustomMultiAgentNodeName,
    NormalSingleAgentNodeName,
    NormalMultiAgentNodeName,
    QueuingSingleAgentNodeName,
    QueuingMultiAgentNodeName,
)

DEBUG: bool = bool(os.environ.get("ARENA_DEBUG", True))  # TODO change to false


@attrs.define()
class _ParsedConfig:
    static: list[Obstacle]
    dynamic: list[DynamicObstacle]


@attrs.define()
class PromptConfig:
    user_prompt: ROSParamT[str]
    generation_mode: ROSParamT[str]


class TM_Prompt(TM_Obstacles):
    """
    Prompt task generator for obstacles.

    This class generates obstacles based on a prompt configuration.

    Attributes:
        _config (Config): Configuration object for obstacle generation.

    Methods:
        __init__(**kwargs): Initializes the TM_Prompt object.
        reset(**kwargs): Resets the obstacle generation with the specified parameters.
    """

    _config: PromptConfig

    def llm_bt_output_to_config(
        self,
        llm_response: EmergencyResponseSchema
        | CustomResponseSchema
        | NormalResponseSchema
        | QueuingResponseSchema,
        *,
        crowd_pedestrians: None | List[Dict],
    ) -> dict:
        try:
            config = {"static": [], "dynamic": []}

            # Emergency mode does not use global planner
            if isinstance(llm_response, EmergencyResponseSchema):
                parser = Parser(llm_response.model_dump())
                parser.parse()
                
                self._logger.info("Generating velocity field...")

                vfgp = ArenaVelocityFieldGenerationPipeline(
                    ArenaVelocityFieldGenerationPipelineConfig(),
                    self.node._world_manager.world,
                )

                velocity_field = vfgp.generate(
                    llm_response
                )  # (n_groups, 64, 64, 2) (g, y, x, 2)

                vel_res = self.send_velocity_msg(velocity_field)
                self._logger.info(
                    f"Set velocity field response: {vel_res.success}, {vel_res.message}"
                )

                self.velocity_field_visualizer.publish_markers(velocity_field)

                with tempfile.NamedTemporaryFile(
                    delete=False,
                    prefix="velocity_field_",
                    suffix=".npy",
                    dir=self.tmp_dir.name,
                    mode="wb",
                ) as file:
                    np.save(file, velocity_field)
                    self._logger.info(f"Saved velocity field to {file.name}")


            else:
                parser = Parser(
                    llm_response.model_dump(),
                    use_global_planner=True,
                    world=self.node._world_manager.world,
                )
                parser.parse()
                waypoints = parser.waypoints
                self.waypoint_visualizer.publish_markers(waypoints)

            for hunav_agent in parser.agents.values():
                hunav_config = {
                    "id": hunav_agent.id,
                    "name": hunav_agent.name,
                    "pos": hunav_agent.pos,
                    "model": hunav_agent.model,
                    "waypoints": hunav_agent.waypoints,
                }

                behavior_tree_xml = hunav_agent.to_xml()

                tmp_xml_file = tempfile.NamedTemporaryFile(
                    mode="w+t", suffix=".xml", dir=self.tmp_dir.name, delete=False
                )

                tmp_xml_file.write(
                    ET.tostring(
                        behavior_tree_xml,
                        encoding="UTF-8",
                        method="xml",
                        xml_declaration=True,
                    ).decode("utf-8")
                )

                hunav_config.update({"behavior_tree": tmp_xml_file.name})

                config["dynamic"].append(hunav_config)

        except Exception as e:
            self._logger.error(f"Failed to parse Behavior tree from LLM response: {e}")
            self._logger.error("Returning empty config!")
            config = {}

        return config

    def setup_chroma(self):
        if os.path.isdir(CHROMA_DB_PATH):
            self.chroma_collection = get_chroma_collection(
                CHROMA_DB_PATH, self.inference_client
            )
        else:
            processed_doc = process_json_doc(BT_REF_DOC_PATH)
            self._logger.info(
                "Creating Chroma DB from Behavior Tree Nodes Reference..."
            )
            self.chroma_collection = create_chroma_db(
                documents=processed_doc,
                db_path=CHROMA_DB_PATH,
                client=self.inference_client,
            )

    def send_velocity_msg(self, velocity_field: np.ndarray):
        n_groups, h, w, c = velocity_field.shape
        msg = Float32MultiArray()
        msg.data = velocity_field.astype(np.float32).flatten(order="C").tolist()
        msg.layout.dim = [
            MultiArrayDimension(label="G", size=n_groups, stride=n_groups * h * w * c),
            MultiArrayDimension(label="H", size=h, stride=h * w * c),
            MultiArrayDimension(label="W", size=w, stride=w * c),
            MultiArrayDimension(label="C", size=c, stride=c),
        ]

        req = SetVelocityField.Request()
        req.velocity_field = msg

        response: SetVelocityField.Response = self.velocity_field_client.call(req)

        return response

    def send_arena_world_bounds_msg(self):
        # TODO: Optimize
        # Get Arena World size
        x_min, y_min, x_max, y_max = np.inf, np.inf, -np.inf, -np.inf

        for zones in self._PROPS.world_manager.world.zones:
            x_min, y_min, x_max, y_max = (
                min(x_min, *(corner.x for corner in zones.corners)),
                min(y_min, *(corner.y for corner in zones.corners)),
                max(x_max, *(corner.x for corner in zones.corners)),
                max(y_max, *(corner.y for corner in zones.corners)),
            )
        arena_world_bounds = [x_min, y_min, x_max, y_max]

        msg = Float32MultiArray()
        msg.data = arena_world_bounds
        msg.layout.dim = [
            MultiArrayDimension(label="bounds", size=4, stride=4),
        ]

        req = SetArenaWorldBounds.Request()
        req.arena_world_bounds = msg

        response: SetArenaWorldBounds.Response = self.arena_world_bounds_client.call(
            req
        )

        return response, x_min, y_min, x_max, y_max

    def get_relevant_zones(self, prompt: str) -> str:
        world_metadata: str = get_world_metatdata(self._PROPS.world_manager.world)

        res = self.inference_client.models.generate_content(
            model=REMOTE_FAST_LM,
            contents=f"Prompt: {prompt}\nWorld metadata: {world_metadata}",
            config=genai.types.GenerateContentConfig(
                system_instruction=(
                    "Extract the relevant zones of the world from the user prompt. "
                    "A relevant zone is where an agent could be spawned or disposed "
                    "based on the user's prompt. Return a JSON list of zone names."
                ),
                response_mime_type="application/json",
                response_schema={
                    "type": "array",
                    "items": {"type": "string"},
                },
                thinking_config=genai.types.ThinkingConfig(
                    include_thoughts=False, thinking_budget=0
                ),
                temperature=0.2,  # Most of the example prompts use this set of parameters, see https://docs.cloud.google.com/vertex-ai/generative-ai/docs/prompt-gallery/samples/extract_tech_specs
                top_k=40,
            ),
        )

        if res.text is None:
            self._logger.warn(
                "Couldn't get relevant zones, returning full world description"
            )
            relevant_zones_names = [
                zone.name for zone in self.node._world_manager.world.zones
            ]
        else:
            adapter = TypeAdapter(List[str])
            relevant_zones_names = adapter.validate_json(res.text)

        relevant_zones = get_world_detail_info(
            self.node._world_manager.world, relevant_zones_names
        )

        return relevant_zones

    def cache_context(self, generation_mode: str):
        self._logger.info(f"Caching context for generation mode: {generation_mode}")
        if generation_mode == GenerationMode.EMERGENCY.value:
            if generation_mode not in self.cached_context_name.keys():
                cache = self.inference_client.caches.create(
                    model=REMOTE_REASONING_LM,
                    config=genai.types.CreateCachedContentConfig(
                        display_name=generation_mode + "_context",
                        system_instruction=SYSTEM_INSTRUCTION,
                        contents=EMERGENCY_MODE,
                    ),
                )
                if cache.name is not None:
                    self.cached_context_name.update({generation_mode: cache.name})

        elif generation_mode == GenerationMode.CUSTOM.value:
            if generation_mode not in self.cached_context_name.keys():
                cache = self.inference_client.caches.create(
                    model=REMOTE_REASONING_LM,
                    config=genai.types.CreateCachedContentConfig(
                        display_name=generation_mode + "_context",
                        system_instruction=SYSTEM_INSTRUCTION,
                        contents=CUSTOM_MODE,
                    ),
                )
                if cache.name is not None:
                    self.cached_context_name.update({generation_mode: cache.name})

        elif generation_mode == GenerationMode.NORMAL.value:
            if generation_mode not in self.cached_context_name.keys():
                cache = self.inference_client.caches.create(
                    model=REMOTE_REASONING_LM,
                    config=genai.types.CreateCachedContentConfig(
                        display_name=generation_mode + "_context",
                        system_instruction=SYSTEM_INSTRUCTION,
                        contents=NORMAL_MODE,
                    ),
                )
                if cache.name is not None:
                    self.cached_context_name.update({generation_mode: cache.name})

        elif generation_mode == GenerationMode.QUEUING.value:
            if generation_mode not in self.cached_context_name.keys():
                cache = self.inference_client.caches.create(
                    model=REMOTE_REASONING_LM,
                    config=genai.types.CreateCachedContentConfig(
                        display_name=generation_mode + "_context",
                        system_instruction=SYSTEM_INSTRUCTION,
                        contents=QUEUING_MODE,
                    ),
                )
                if cache.name is not None:
                    self.cached_context_name.update({generation_mode: cache.name})

    async def _prompt_to_config(
        self, prompt: str, generation_mode: str, local: bool = False
    ) -> dict:
        messages = []
        crowd_pedestrians = None

        pipeline_start = time.time()
        self.cache_context(generation_mode)

        relevant_zones = self.get_relevant_zones(prompt)
        response_schema = None

        if generation_mode == GenerationMode.EMERGENCY.value:
            response_schema = EmergencyResponseSchema

            bt_nodes = get_relevant_bt_nodes(
                query=f"Retrieve information of these nodes: {str(list(get_args(EmergencySingleAgentNodeName)) + list(get_args(EmergencyMultiAgentNodeName)))}",
                collection=self.chroma_collection,
                n_results=3
            )

            self._logger.warn(f"Choosen bt_nodes: {bt_nodes}")

            messages.append(
                f"Generate hunav agents data for a simulation where {prompt}. "
                f"Generate data base on this world data as below <WORLD_DESCRIPTION>: {relevant_zones}. "
                f"Use these behavior tree nodes only: {bt_nodes}."
            )

            arena_world_bounds_res, x_min, y_min, x_max, y_max = (
                self.send_arena_world_bounds_msg()
            )
            self._logger.info(
                f"Set Arena World bounds response: {arena_world_bounds_res.success}, {arena_world_bounds_res.message}"
            )
            self.velocity_field_visualizer.update_world_bounds(
                x_min, y_min, x_max, y_max
            )

        elif generation_mode == GenerationMode.CUSTOM.value:
            response_schema = CustomResponseSchema

            bt_nodes = get_relevant_bt_nodes(
                query=f"Retrieve information of these nodes: {str(list(get_args(CustomSingleAgentNodeName)) + list(get_args(CustomMultiAgentNodeName)))}",
                collection=self.chroma_collection,
            )

            self._logger.warn(f"Choosen bt_nodes: {bt_nodes}")

            messages.append(
                f"Generate hunav agents data for a simulation where {prompt}. "
                f"Generate data base on this world data as below <WORLD_DESCRIPTION>: {relevant_zones}. "
                f"Use these behavior tree nodes only: {bt_nodes}."
            )

            # Split prompts for Ambient Agents and Spotlight agent
            split_prompt_res = self.inference_client.models.generate_content(
                model=REMOTE_FAST_LM,
                contents=f"Split prompts given this user prompt: {prompt}",
                config=genai.types.GenerateContentConfig(
                    system_instruction=SPLIT_PROMPT_INSTRUCTION,
                    temperature=0.2,
                    top_k=40,
                    response_mime_type="application/json",
                    response_json_schema=Dict[
                        Literal["spotlight_agents_prompt", "ambient_agents_prompt"], str
                    ],
                    thinking_config=genai.types.ThinkingConfig(
                        include_thoughts=False, thinking_budget=0
                    ),
                ),
            )
            splited_prompts = split_prompt_res.text
            assert splited_prompts is not None
            splited_prompts = TypeAdapter(
                Dict[Literal["spotlight_agents_prompt", "ambient_agents_prompt"], str]
            ).validate_json(splited_prompts)

            prompt = splited_prompts["spotlight_agents_prompt"]
            ambient_agent_prompt = splited_prompts["ambient_agents_prompt"]

            self._logger.info(
                f"Spotlight Agents prompts: {prompt}\nAmbient_agents_prompt:{ambient_agent_prompt}"
            )

            cgp_config = ATCPConfig(
                visual=False,
                save_path=os.path.join(
                    get_package_share_directory("arena_text_crowd"),
                    "generated_velocity_field",
                ),
                model=REMOTE_REASONING_LM,
            )
            # text_crowd_unet_dir = os.path.join(
            #     get_package_share_directory("arena_text_crowd"),
            #     "models",
            #     "velocity_field_generation",
            #     "sd_unet_2d_conditioned",
            # )
            text_crowd_unet_dir = "/home/linh/ductai_nguyen_ws/Text-Crowd/text_crowd/Language_Crowd_Animation/Models_Server_ForTest/Field-Full-V2/checkpoint-270000/unet"
            vfgp_config = VFGPConfig(unet_dir=text_crowd_unet_dir)
            cgp = CrowdGenerationPipeline(cgp_config, vfgp_config)

            arena_world_bounds_res, x_min, y_min, x_max, y_max = (
                self.send_arena_world_bounds_msg()
            )
            self._logger.info(
                f"Set Arena World bounds response: {arena_world_bounds_res.success}, {arena_world_bounds_res.message}"
            )
            self.velocity_field_visualizer.update_world_bounds(
                x_min, y_min, x_max, y_max
            )

            scenario, arena_entity_to_semantic_entity_map = (
                arena_world_to_text_crowd_scenario(
                    self._PROPS.world_manager.world, scenario_size=(1024, 1024)
                )
            )

            self._logger.info("Generating velocity field...")
            velocity_field, crowd_pedestrians, text_crowd_scenario = cgp.generate(
                prompt=ambient_agent_prompt,
                scenario=scenario,
                arena_world_description=self._PROPS.world_manager.world,
                arena_entity_to_semantic_entity_map=arena_entity_to_semantic_entity_map,
            )  # (n_groups, 64, 64, 2) (g, y, x, 2)

            vel_res = self.send_velocity_msg(velocity_field)
            self._logger.info(
                f"Set velocity field response: {vel_res.success}, {vel_res.message}"
            )

            self.velocity_field_visualizer.publish_markers(velocity_field)

            with tempfile.NamedTemporaryFile(
                delete=False,
                prefix="velocity_field_",
                suffix=".npy",
                dir=self.tmp_dir.name,
                mode="wb",
            ) as file:
                np.save(file, velocity_field)
                self._logger.info(f"Saved velocity field to {file.name}")
            with tempfile.NamedTemporaryFile(
                delete=False,
                prefix="text_crowd_scenario_",
                suffix=".pkl",
                dir=self.tmp_dir.name,
                mode="wb",
            ) as file:
                pickle.dump(text_crowd_scenario, file)

        elif generation_mode == GenerationMode.NORMAL.value:
            response_schema = NormalResponseSchema

            bt_nodes = get_relevant_bt_nodes(
                query=f"Retrieve information of these nodes: {str(list(get_args(NormalSingleAgentNodeName)) + list(get_args(NormalMultiAgentNodeName)))}",
                collection=self.chroma_collection,
            )

            self._logger.warn(f"Choosen bt_nodes: {bt_nodes}")

            messages.append(
                f"Generate hunav agents data for a simulation where {prompt}. "
                f"Generate data base on this world data as below <WORLD_DESCRIPTION>: {relevant_zones}. "
                f"Use these behavior tree nodes only: {bt_nodes}."
            )

        elif generation_mode == GenerationMode.QUEUING.value:
            response_schema = QueuingResponseSchema

            bt_nodes = get_relevant_bt_nodes(
                query=f"Retrieve information of these nodes: {str(list(get_args(QueuingSingleAgentNodeName)) + list(get_args(QueuingMultiAgentNodeName)))}",
                collection=self.chroma_collection,
            )

            self._logger.warn(f"Choosen bt_nodes: {bt_nodes}")

            messages.append(
                f"Generate hunav agents data for a simulation where {prompt}. "
                f"Generate data base on this world data as below <WORLD_DESCRIPTION>: {relevant_zones}. "
                f"Use these behavior tree nodes only: {bt_nodes}."
            )
        else:
            raise ValueError()

        if local:  # Currently not supported
            return {}
            from huggingface_hub import InferenceClient
            from transformers import AutoModelForCausalLM, AutoTokenizer

            # Load tokenizer and model
            tokenizer = AutoTokenizer.from_pretrained(LOCAL_LM, trust_remote_code=True)
            model = AutoModelForCausalLM.from_pretrained(LOCAL_LM)
            # Format using Qwen chat template
            prompt_text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )

            self._logger.info("Start inference...")
            start = time.time()

            # Tokenize input
            inputs = tokenizer([prompt_text], return_tensors="pt").to(model.device)

            # Generate output
            outputs = model.generate(
                **inputs,
                max_new_tokens=32768,
            )

            # Extract generated tokens (excluding prompt)
            generated_ids = outputs[0][len(inputs.input_ids[0]) :]
            answer = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
            end = time.time()
            self._logger.info(f"Inference done, took: {end - start:.1f}s")

        else:
            self._logger.info("Start inference...")
            start = time.time()
            response = await self.inference_client.aio.models.generate_content(
                model=REMOTE_REASONING_LM,
                contents=messages,
                config=genai.types.GenerateContentConfig(
                    cached_content=self.cached_context_name[generation_mode],
                    temperature=0.2,  # Most of the example prompts use this set of parameters, see https://docs.cloud.google.com/vertex-ai/generative-ai/docs/prompt-gallery/samples/extract_tech_specs
                    top_k=40,
                    thinking_config=genai.types.ThinkingConfig(
                        thinking_level=genai.types.ThinkingLevel(value="LOW")
                    ),
                    response_mime_type="application/json",
                    response_json_schema=response_schema.model_json_schema(),
                ),
            )

            assert response.text is not None
            answer = response_schema.model_validate_json(response.text)

            end = time.time()
            self._logger.info(f"Inference done, took: {end - start:.1f}s")

        # Parse it into a Python dict
        config = self.llm_bt_output_to_config(
            answer,
            crowd_pedestrians=crowd_pedestrians,
        )

        pipeline_end = time.time()
        self._logger.info(
            f"Generation pipeline took: {pipeline_end - pipeline_start:.1f}s"
        )

        if DEBUG:
            with tempfile.NamedTemporaryFile(
                delete=False,
                prefix="scenario_",
                suffix=".json",
                dir=self.tmp_dir.name,
                mode="w",
            ) as file:
                json.dump(config, file, indent=2)
                self._logger.warning(f"Saved parsed prompt result to {file.name}")
            with tempfile.NamedTemporaryFile(
                delete=False,
                prefix="llm_response_",
                suffix=".json",
                dir=self.tmp_dir.name,
                mode="w",
            ) as file:
                json.dump(answer.model_dump_json(), file, indent=2)
                self._logger.warning(f"Saved LLM response to {file.name}")
        return config

    async def _parse_prompt(self, prompt: str, generation_mode: str) -> _ParsedConfig:
        """
        Parses the prompt to generate obstacles config.

        Args:
            prompt (str): The prompt for generating obstacles config.

        Returns:
            _ParsedConfig: Parsed configuration containing static and dynamic obstacles.
        """
        assert GenerationMode.has_value(generation_mode)
        config = await self._prompt_to_config(prompt, generation_mode)

        static_obstacles: list[Obstacle]
        dynamic_obstacles: list[DynamicObstacle]

        static_obstacles = [
            # Obstacle.parse(obs)
            # for obs
            # in itertools.chain(
            #     config.get("obstacles", {}).get("static", []),
            #     config.get("obstacles", {}).get("interactive", []),
            # )
            # This causes bug so temporarily disabled
        ]

        dynamic_obstacles = [obs for obs in config.get("dynamic", [])]

        result = converter.structure(
            dict(static=static_obstacles, dynamic=dynamic_obstacles), _ParsedConfig
        )

        return result

    async def reset(self, **kwargs):
        parsed_config = await self._parse_prompt(
            self._config.user_prompt.value,
            self._config.generation_mode.value,
        )

        return parsed_config.static, parsed_config.dynamic

    def __init__(self, **kwargs):
        TM_Obstacles.__init__(self, **kwargs)
        # self.inference_client = InferenceClient(
        #     provider="together",
        #     api_key=os.environ["HF_TOKEN"],
        # )

        # def _load_config(filename: str = "default.yaml") -> "HunavDynamicObstacle":
        #     """Load config from YAML file in arena_bringup configs."""
        #
        #     # second priority: Install space
        #     config_path = os.path.join(
        #         get_package_share_directory("arena_bringup"),
        #         "configs",
        #         "hunav_agents",
        #         filename,
        #     )
        #
        #     try:
        #         with open(config_path, "r") as f:
        #             config = yaml.safe_load(f)
        #
        #         assert isinstance(config, dict), (
        #             "Config file is not properly formatted."
        #         )
        #         agent_config = config["hunav_loader"]["ros__parameters"]["agent1"]
        #         return agent_config
        #
        #     except Exception as e:
        #         raise RuntimeError(f"Error loading config from {config_path}") from e
        #
        # default_hunav_config = _load_config() # Is not used yet

        self._config = PromptConfig(
            user_prompt=self.node.ROSParam[str](
                self.namespace("user_prompt"),
                value="An empty space with no pedestrian.",
            ),
            generation_mode=self.node.ROSParam[str](
                self.namespace("generation_mode"),
                value=GenerationMode.QUEUING.value,
            ),
        )

        if "GEMINI_API_KEY" not in os.environ:
            self._logger.error("GEMINI_API_KEY environment variable not set!")
            raise OSError("GEMINI_API_KEY environment variable not set!")

        self.inference_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

        try:
            caches = self.inference_client.caches.list()
            if caches:
                for cache in caches:
                    if cache.name is not None:
                        self.inference_client.caches.delete(name=cache.name)
        except Exception as e:
            print(e)

        self.cached_context_name: dict[
            str, str
        ] = {}  # Whether the prompt context need to be changed and fed into LLM model

        self.setup_chroma()

        self.tmp_dir = tempfile.TemporaryDirectory(
            dir=os.path.join(
                WorldIdentifier(self.node._world_manager.world_name)
                .resolve_sync()
                .path,
                "scenarios",
            )
        )  # Temporary directory to store behavior tree XML files

        # Velocity field generation
        self.velocity_field_client = self.node.create_client(
            SetVelocityField, "/task_generator_node/set_velocity_field"
        )
        while not self.velocity_field_client.wait_for_service(timeout_sec=1.0):
            self.node.get_logger().info(
                "Waiting for service /task_generator_node/set_velocity_field"
            )
        self.velocity_field_visualizer = VelocityFieldVisualizer(
            self.node,
            topic_name="/task_generator_node/velocity_field_marker",
        )
        self.arena_world_bounds_client = self.node.create_client(
            SetArenaWorldBounds, "/task_generator_node/set_arena_world_bounds"
        )
        while not self.arena_world_bounds_client.wait_for_service(timeout_sec=1.0):
            self.node.get_logger().info(
                "Waiting for service /task_generator_node/set_arena_world_bounds"
            )

        self.waypoint_visualizer = WaypointVisualizer(
            self.node, "/task_generator_node/waypoint_marker"
        )

    def __del__(self):
        try:
            # Delete caches
            for cache_name in self.cached_context_name.values():
                self.inference_client.caches.delete(name=cache_name)
            self.cached_context_name: dict[str, str] = {}
        except Exception as e:
            self._logger.error(e)
            self._logger.error("Can not delete cache! Maybe it was deleted earlier.")
