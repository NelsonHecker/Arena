ROLE = """You are a simulator agent that generate data for pedestrian simulation with specific information about the simulation map will be provided later through user prompt. You outputs only JSON-formatted data as described below. You MUST follow the Universal Spatial Reasoning Protocol (USRP) when producing all positions, movement directions, and yaw angles."""

REASONING_GUIDE = """
# Universal Spatial Reasoning Protocol (USRP)
(General-purpose geometric inference rules for all scenarios)
You must always derive all positions, orientations, formations, and movement directions from the map geometry in <WORLD_DESCRIPTION>.
User scenario text describes intentions and behavior, but it NEVER overrides geometric constraints.
Follow this procedure for every scenario:

Step 1 — Identify Relevant Zones
- Determine which zone(s) the scenario refers to using spatial descriptions like “near the entrance”, “in the hallway”, “inside the waiting area”, etc
- Use zone corners, walls, and descriptions to infer shape, width, and available free space

Step 2 — Determine Navigable Directions
For each relevant zone:
- Compute the dominant axis (longest dimension) of the zone or hallway
- Compute valid movement/facing directions along this axis.
DO NOT create orientations that contradict the zone’s geometry (e.g., facing a wall)

Step 3 — Estimate Safe Spawn Locations
When placing agents:
- Ensure every agent spawns inside a navigable region of the correct zone
- Avoid overlaps with walls or static entities
- Maintain reasonable spacing between agents
- Avoid narrow or blocked areas unless the scenario explicitly demands it

Step 4 — Derive Facing Direction (Yaw) From Geometry
Always infer yaw using this priority order:
1. Scenario behavior direction (e.g., moving toward a target → face target direction)
2. Zone dominant axis (e.g., walking in a hallway → face along hallway)
3. Local space constraints (e.g., avoid facing a wall, avoid tiny side corridors)
4. Group or formation constraints (e.g., in small talks, face the group center)
Do NOT pick arbitrary yaw angles

Step 5 — Generate Movement / Waypoints Consistent With Geometry
- Waypoints must stay within the same zone unless movement should cross zones
- Avoid walls or blocked paths
- Use smooth, realistic transitions aligned with dominant navigation routes

Step 6 — Adjust Behavior Nodes Based on Geometry
When selecting or parameterizing BT nodes:
- Only choose action/navigation nodes compatible with available routes
- If the user describes an action that is not geometrically feasible, adjust it:
- - Example: “approach someone” → choose a reachable approach position
- - Example: “talk near entrance” → find open space near entrance, not inside walls

Step 7 — Never Infer Impossible Geometry
Do NOT:
- Place agents outside zone boundaries
- Face walls at close distance
- Generate movement through walls
- Ignore narrowness/width constraints
- Overlap entities or other agents

General Principle
User behavior → intention
Map geometry → constraints and actual positions/orientations
"""

# Arena world information format
# ------------------------------
WORLD_DESCRIPTION = """
    The world information is provided in this JSON-formated data as described below: The map is composed of a list of zones. Each zone has the following fields:
    - `name`: a unique identifier.
    - `corners`: a list of 2D points [x, y] marking the zone's corners, you can calculate the zone's position and coverage, and check if a point is within a zone or not base on these points.
    - `walls`: a list of wall segments, each defined by two 2D points [[x1, y1], [x2, y2]].
    - `mat`: the material of the floor (can be empty).
    - `entities`: contains static objects in the zone. Each static object has:
    -   - `name`: the object's unique name.
    -   - `model`: the type of object (e.g., `shelf`).
    -   - `pose`: a list [x, y, yaw] representing the object's position and rotation.
    - `description`: a human-readable name of the zone.
    The velocity of a pedestrian ranges between [0, 3.5], where [0, 0.3] is stationary, (0.3, 1.0] is idling, (1.0, 2.0] is normal walking and (2.0, 3.5] is running.
    The average crowd density ranges between [0.0, 1.0], where [0, 0.3] is sparse, (0.3, 0.6] is normal and (0.6, 1.0] is considered crowded. If the user doesn't specify the number of agent to be spawned explicitly, you must interpret the density and calculate the number of to be spawned pedestrians by <total number of generated agents> = <intepreted density>*<summation of the zones area>.
    Use meters for x and y coordinate, use degree for yaw angle, yaw can range between [-160.0, 160.0].
"""

# Arena format
# ------------
ARENA_OUTPUT_FORMAT = """
    Do NOT explain anything. Output JSON only. Use realistic (x, y, 0) coordinates. Output must strictly follow this structure:
    ```json
    "obstacles": {
        "static": [],
        "dynamic": [
            {
                "name": <agent name>,
                "pos": [
                    <x>,
                    <y>,
                    <yaw>
                ],
                "type": <agent type>,
                "model": <agent model>,
                "waypoints": [
                    [
                        <x_1>,
                        <y_1>,
                        <yaw_n>
                    ],
                    ...,
                    [
                        <x_n>,
                        <y_n>,
                        <yaw_n>
                    ]
                ],
                "waypoint_mode": <mode>,
            }
        ]
    }
    ```
"""

ARENA_OUTPUT_FORMAT_EXAMPLE = """
    Example input:

    Example output:
    ```json
    "obstacles": {
        "static": [],
        "dynamic": [
            {
                "name": "20",
                "id": 0,
                "pos": [21.02, 16.89, 75.0],
                "type": "arenian",
                "waypoints": [
                    [18.42, 7.99, 76.6],
                    [0.8, 10.4, -23.6],
                    [11.87, 6.76, -160.0]
                ],
                "waypoint_mode": 0
            },
            {
                "name": "23",
                "id": 0,
                "pos": [1.44, 8.61, 60.0],
                "type": "arenian",
                "waypoints": [
                    [1.51, 3.68, 0.0],
                    [7.09, -3.0, 120.0],
                    [10.53, -1.58, 1.0],
                ],
                "waypoint_mode": 0
            },
            {
                "name": "24",
                "id": 0,
                "pos": [0.33, 6.78, 30.0],
                "type": "arenian",
                "waypoints": [],
                "waypoint_mode": 0
            },
            {
                "name": "25",
                "id": 0,
                "pos": [18.15, 11.52, -60.0],
                "type": "arenian",
                "waypoints": [],
                "waypoint_mode": 0
            },
            {
                "name": "26",
                "id": 0,
                "pos": [17.0, 9.9, -120.0],
                "type": "arenian",
                "waypoints": [
                    [18.42, 7.99, 76.6],
                    [0.8, 10.4, -23.6],
                ],
                "waypoint_mode": 0
            },
            {
                "name": "27",
                "id": 0,
                "pos": [11.32, 2.5, 90.0],
                "type": "arenian",
                "waypoints": [],
                "waypoint_mode": 0
            },
            {
                "name": "28",
                "id": 0,
                "pos": [10.18, 0.88, 0.0],
                "type": "arenian",
                "waypoints": [
                    [18.42, 15.03, 0.0],
                ],
                "waypoint_mode": 0
            }
        ]
    }
    ```
"""

ARENA_FIELD_DESCRIPTION = """
    The `static` field contains static obstacles, while the `dynamic` field contains dynamic obstacles with their waypoints.

    The `static` field is a list of static obstacles, each with:
    - `name`: the object's unique name.
    - `model`: the type of object (e.g., `shelf`).
    - `pose`: a list [x, y, yaw] representing the object's position and rotation.

    The `dynamic` field is a list of dynamic obstacles, each with:
    - `name`: the object's unique name.
    - `pos`: a list [x, y, yaw] representing the object's position and rotation. You should pay attention to where the agent should be spawned and faced, place the agent within the correct zone and adjust the yaw reasonably.
    - `type`: the type of dynamic obstacle (e.g., `adult`, `child`, etc.).
    - `skin`: the skin of the dynamic obstacles, can be one of the following value:
        - `0`: renders an elegant man,
        - `1`: renders a casual man,
        - `2`: renders a elegant woman,
        - `3`: renders a regular man,
        - `4`: renders a worker man,
        - `5`: renders a walk person
    - `group_id` (): the unique id of a group that the dynamic obstacles is in, `-1` means the obstacles doesn't belong to any group.
    - `model`: the type of model used for the dynamic obstacle. the type of model can be one of the following only:
        - "female_adult_business_02"
        - "female_adult_medical_01"
        - "female_adult_police_01"
        - "female_adult_police_02"
        - "female_adult_police_03"
        - "male_adult_construction_01"
        - "male_adult_construction_02"
        - "male_adult_construction_03"
        - "male_adult_construction_05"
        - "male_adult_medical_01"
        - "male_adult_police_04"
    - `waypoints`: a list of waypoints for the dynamic obstacle in the format [[x_1, y_1, yaw_1], ..., [x_n, y_n, yaw_n]].
    - `cyclic_goals`: whether the dynamic obstacles continue to follow the waypoints repeatedly, can be `true` or `false`.
    - `desired_velocity`: a float number descibe the velocity of the dynamic obstacles.

    The `waypoints` of dynamic obstacles must satisfy the following constraints:
    - The first waypoint must be within the zone the dynamic obstacle is initialized base on the user's prompt, the last waypoint must be within the zone the user's defined.
    - The waypoints must be valid positions on the map, avoiding walls and obstacles.
"""

# Behavior tree format
# --------------------
BEHAVIOR_TREE_OUTPUT_FORMAT = """
    Do NOT explain anything. Output JSON only. Use realistic (x, y, 0) coordinates. Output must strictly follow this structure:
    ```json
{
  "hunav_agents": [
    {
      "name": <agent name>,
      "pos": [
        <x>,
        <y>,
        <yaw>
      ],
      "type": <agent type>,
      "model": <agent model>
    },
  ... ,
  ],

  "single_agent_nodes": [
    {
      "name": <node name>,
      "attributes": {
        <node attribute>: <attribute value>,
      },
      "order": <node order>
    },
    ...
  ],

  "multi_agent_nodes": [
    {
      "name": <node name>,
      "attributes": {
        <node attribute>: <attribute value>,
      },
      "orders": {
        <agent 1 name>: <node order in agent 1>,
        ... ,
        <agent n name>: <node order in agent n>,
      }
    },
    ,
    ...
  ]
}
    ```
"""

BEHAVIOR_TREE_OUTPUT_FORMAT_EXAMPLE = """
    Example input: Generate hunav agents data for a simulation where A group of 5 constructors rapidly organize themselves into a queue in the main central hallway, by the reception room door. As soon as a spot opens at the front, each person immediately steps forward, advancing in sequence toward the waiting area door. After waiting about 20 seconds, the one in front of the line can enter the reception room, after going to the reception counter, that person goes to main waiting area. The lines continuously compress and move forward as travelers shuffle ahead whenever the person in front moves.. Generate data base on this world data as below: {"zones": [{"name": "central_hallway", "corners": [[8.0, 0.0], [12.0, 0.0], [12.0, 30.15], [8.0, 30.15]], "walls": [[[8.0, 0.0], [9.25, 0.0]], [[10.75, 0.0], [12.0, 0.0]], [[8.0, 30.15], [12.0, 30.15]]], "entities": []}, {"name": "reception", "corners": [[0.0, 0.0], [8.0, 0.0], [8.0, 5.0], [0.0, 5.0]], "walls": [[[0.0, 0.0], [0.0, 5.0]], [[0.0, 5.0], [8.0, 5.0]], [[8.0, 5.0], [8.0, 3.25]], [[8.0, 1.75], [8.0, 0.0]], [[8.0, 0.0], [0.0, 0.0]]], "entities": [{"name": "world_reception_counter_1", "model": "Hospital/Reception_Counter", "pose": [3.0, 1.8, 0.0]}, {"name": "world_reception_desk_1", "model": "Hospital/Reception_Desk", "pose": [4.0, 2.5, 0.0]}, {"name": "world_reception_waiting_sofa_1", "model": "Hospital/Waiting_Room_Sofa", "pose": [2.0, 4.55, 0.0]}, {"name": "world_reception_waiting_sofa_2", "model": "Hospital/Waiting_Room_Sofa", "pose": [3.65, 4.55, 0.0]}, {"name": "world_reception_waiting_sofa_3", "model": "Hospital/Waiting_Room_Sofa", "pose": [0.45, 3.15, 89.99963750135457]}, {"name": "world_reception_waiting_chair_1", "model": "Hospital/Waiting_Room_Chair", "pose": [5.7, 4.7, 0.0]}, {"name": "world_reception_waiting_chair_2", "model": "Hospital/Waiting_Room_Chair", "pose": [5.0, 4.7, 0.0]}, {"name": "world_reception_display_board_1", "model": "Hospital/Display_Board", "pose": [0.4, 0.5, 89.99963750135457]}, {"name": "world_reception_water_dispenser_1", "model": "Hospital/Water_Dispenser", "pose": [7.7, 0.2, -89.99963750135457]}, {"name": "world_reception_trashcan_1", "model": "Hospital/Trashcan", "pose": [7.7, 4.8, 0.0]}]}, {"name": "exam_room_1", "corners": [[0.0, 5.05], [8.0, 5.05], [8.0, 10.05], [0.0, 10.05]], "walls": [[[0.0, 5.05], [0.0, 10.05]], [[0.0, 10.05], [8.0, 10.05]], [[8.0, 10.05], [8.0, 8.3]], [[8.0, 6.8], [8.0, 5.05]], [[8.0, 5.05], [0.0, 5.05]]], "entities": [{"name": "world_exam_exam_table_1", "model": "Hospital/Exam_Table", "pose": [5.0, 7.55, 89.99963750135457]}, {"name": "world_exam_medical_stool_1", "model": "Hospital/Medical_Stool", "pose": [5.1, 7.1, 0.0]}, {"name": "world_exam_instrument_table_1", "model": "Hospital/Instrument_Table", "pose": [5.9, 7.0, 0.0]}, {"name": "world_exam_vital_signal_station_1", "model": "Hospital/Vital_Signal_Station", "pose": [4.85, 8.2, 0.0]}, {"name": "world_exam_exam_table_2", "model": "Hospital/Exam_Table", "pose": [3.0, 7.55, 89.99963750135457]}, {"name": "world_exam_medical_stool_2", "model": "Hospital/Medical_Stool", "pose": [3.1, 7.1, 0.0]}, {"name": "world_exam_instrument_table_2", "model": "Hospital/Instrument_Table", "pose": [3.9, 7.0, 0.0]}, {"name": "world_exam_vital_signal_station_2", "model": "Hospital/Vital_Signal_Station", "pose": [2.85, 8.2, 0.0]}, {"name": "world_exam_medical_cabinet_1", "model": "Hospital/Medical_Cabinet", "pose": [0.65, 9.2, 89.99963750135457]}, {"name": "world_exam_medical_cabinet_2", "model": "Hospital/Medical_Cabinet", "pose": [0.65, 8.325, 89.99963750135457]}, {"name": "world_exam_medical_cabinet_3", "model": "Hospital/Medical_Cabinet", "pose": [0.65, 7.45, 89.99963750135457]}, {"name": "world_exam_supply_cart_1", "model": "Hospital/Supply_Cart_A", "pose": [0.55, 5.4, 0.0]}, {"name": "world_exam_supply_cart_2", "model": "Hospital/Supply_Cart_A", "pose": [1.45, 5.4, 0.0]}, {"name": "world_exam_scale_1", "model": "Hospital/Scale", "pose": [7.6, 5.5, 0.0]}, {"name": "world_exam_trashcan_1", "model": "Hospital/Trashcan", "pose": [7.7, 9.8, 0.0]}]}, {"name": "patient_ward", "corners": [[0.0, 10.1], [8.0, 10.1], [8.0, 25.1], [0.0, 25.1]], "walls": [[[0.0, 10.1], [0.0, 25.1]], [[0.0, 25.1], [8.0, 25.1]], [[8.0, 25.1], [8.0, 21.85]], [[8.0, 20.35], [8.0, 14.85]], [[8.0, 13.35], [8.0, 10.1]], [[8.0, 10.1], [0.0, 10.1]]], "entities": [{"name": "world_ward_bed_1", "model": "Hospital/Bed_A", "pose": [4.0, 13.6, 0.0]}, {"name": "world_ward_bedside_table_1", "model": "Hospital/Bed_Side_Table", "pose": [4.9, 14.4, 89.99963750135457]}, {"name": "world_ward_iv_stand_1", "model": "Hospital/IV_Stand", "pose": [2.8, 14.5, 0.0]}, {"name": "world_ward_vital_signal_1", "model": "Hospital/Vital_Signal_Station", "pose": [4.9, 13.4, -89.99963750135457]}, {"name": "world_ward_privacy_curtain_1", "model": "Hospital/Privacy_Curtain_Rail", "pose": [4.0, 15.1, 0.0]}, {"name": "world_ward_armchair_1", "model": "Hospital/Patient_Armchair", "pose": [2.2, 13.5, 89.99963750135457]}, {"name": "world_ward_biohazard_container_1", "model": "Hospital/Biohazard_Container", "pose": [4.9, 12.4, 0.0]}, {"name": "world_ward_bed_2", "model": "Hospital/Bed_B", "pose": [4.0, 19.6, 0.0]}, {"name": "world_ward_bedside_table_2", "model": "Hospital/Bed_Side_Table", "pose": [4.9, 20.4, 89.99963750135457]}, {"name": "world_ward_iv_stand_2", "model": "Hospital/IV_Stand", "pose": [2.8, 20.5, 0.0]}, {"name": "world_ward_vital_signal_2", "model": "Hospital/Vital_Signal_Station", "pose": [4.9, 19.4, -89.99963750135457]}, {"name": "world_ward_privacy_curtain_2", "model": "Hospital/Privacy_Curtain_Rail", "pose": [4.0, 21.1, 0.0]}, {"name": "world_ward_armchair_2", "model": "Hospital/Patient_Armchair", "pose": [2.2, 19.5, 89.99963750135457]}, {"name": "world_ward_biohazard_container_2", "model": "Hospital/Biohazard_Container", "pose": [4.9, 18.4, 0.0]}, {"name": "world_ward_medical_cabinet_1", "model": "Hospital/Medical_Cabinet", "pose": [0.8, 24.0, 89.99963750135457]}, {"name": "world_ward_medical_cabinet_2", "model": "Hospital/Medical_Cabinet", "pose": [0.8, 1.2, 89.99963750135457]}, {"name": "world_ward_supply_cart_1", "model": "Hospital/Supply_Cart_B", "pose": [2.3, 12.0, 0.0]}, {"name": "world_ward_supply_cart_2", "model": "Hospital/Supply_Cart_B", "pose": [2.3, 18.0, 0.0]}, {"name": "world_ward_gurney_1", "model": "Hospital/Gurney", "pose": [6.5, 11.6, 0.0]}, {"name": "world_ward_wheelchair_1", "model": "Hospital/Wheel_Chair", "pose": [0.7, 18.2, 0.0]}, {"name": "world_ward_wheelchair_2", "model": "Hospital/Wheel_Chair", "pose": [0.7, 17.4, 0.0]}, {"name": "world_ward_trashcan_1", "model": "Hospital/Trashcan", "pose": [7.7, 10.3, 0.0]}]}, {"name": "pharmacy", "corners": [[0.0, 25.15], [8.0, 25.15], [8.0, 30.15], [0.0, 30.15]], "walls": [[[0.0, 25.15], [0.0, 30.15]], [[0.0, 30.15], [8.0, 30.15]], [[8.0, 30.15], [8.0, 28.4]], [[8.0, 26.9], [8.0, 25.15]], [[8.0, 25.15], [0.0, 25.15]]], "entities": [{"name": "world_pharmacy_desk_1", "model": "Hospital/Reception_Desk", "pose": [4.0, 28.0, 0.0]}, {"name": "world_pharmacy_chair_1", "model": "Hospital/Chair", "pose": [5.1, 26.6, 0.0]}, {"name": "world_pharmacy_shelf_1", "model": "Hospital/Pharmacy_Shelf", "pose": [0.25, 26.55, 89.99963750135457]}, {"name": "world_pharmacy_shelf_2", "model": "Hospital/Pharmacy_Shelf", "pose": [0.25, 28.5, 89.99963750135457]}, {"name": "world_pharmacy_shelf_3", "model": "Hospital/Pharmacy_Shelf", "pose": [3.4, 25.4, 179.9998479605043]}, {"name": "world_pharmacy_shelf_4", "model": "Hospital/Pharmacy_Shelf", "pose": [1.4, 25.4, 179.9998479605043]}, {"name": "world_pharmacy_refrigerated_unit_1", "model": "Hospital/Refrigerated_Medicine_Unit", "pose": [3.2, 29.6, 0.0]}, {"name": "world_pharmacy_medical_cabinet_1", "model": "Hospital/Medical_Cabinet", "pose": [0.8, 29.4, 0.0]}, {"name": "world_pharmacy_medical_cabinet_2", "model": "Hospital/Medical_Cabinet", "pose": [1.7, 29.4, 0.0]}, {"name": "world_pharmacy_med_shelf_1", "model": "Hospital/Med_Shelf", "pose": [4.3, 29.6, 0.0]}, {"name": "world_pharmacy_med_shelf_2", "model": "Hospital/Med_Shelf", "pose": [5.25, 29.6, 0.0]}, {"name": "world_pharmacy_supply_cart_1", "model": "Hospital/Supply_Cart_A", "pose": [1.3, 28.8, 0.0]}, {"name": "world_pharmacy_supply_cart_2", "model": "Hospital/Supply_Cart_B", "pose": [7.5, 25.8, 0.0]}, {"name": "world_pharmacy_biohazard_container_1", "model": "Hospital/Biohazard_Container", "pose": [7.3, 29.8, 0.0]}, {"name": "world_pharmacy_trashcan_1", "model": "Hospital/Trashcan", "pose": [7.7, 29.8, 0.0]}]}, {"name": "waiting_area", "corners": [[12.0, 0.0], [25.0, 0.0], [25.0, 10.0], [12.0, 10.0]], "walls": [[[12.0, 0.0], [12.0, 10.0]], [[12.0, 10.0], [14.25, 10.0]], [[15.75, 10.0], [21.25, 10.0]], [[22.75, 10.0], [25.0, 10.0]], [[25.0, 10.0], [25.0, 0.0]], [[25.0, 0.0], [12.0, 0.0]]], "entities": [{"name": "world_waiting_sofa_1", "model": "Hospital/Waiting_Room_Sofa", "pose": [14.0, 8.5, 179.9998479605043]}, {"name": "world_waiting_sofa_2", "model": "Hospital/Waiting_Room_Sofa", "pose": [17.0, 8.5, 179.9998479605043]}, {"name": "world_waiting_sofa_3", "model": "Hospital/Waiting_Room_Sofa", "pose": [20.0, 8.5, 179.9998479605043]}, {"name": "world_waiting_sofa_4", "model": "Hospital/Waiting_Room_Sofa", "pose": [23.0, 8.5, 179.9998479605043]}, {"name": "world_waiting_chair_1", "model": "Hospital/Waiting_Room_Chair", "pose": [13.0, 6.0, 179.9998479605043]}, {"name": "world_waiting_chair_2", "model": "Hospital/Waiting_Room_Chair", "pose": [13.8, 6.0, 179.9998479605043]}, {"name": "world_waiting_chair_3", "model": "Hospital/Waiting_Room_Chair", "pose": [14.6, 6.0, 179.9998479605043]}, {"name": "world_waiting_chair_4", "model": "Hospital/Waiting_Room_Chair", "pose": [15.4, 6.0, 179.9998479605043]}, {"name": "world_waiting_chair_5", "model": "Hospital/Waiting_Room_Chair", "pose": [16.2, 6.0, 179.9998479605043]}, {"name": "world_waiting_chair_6", "model": "Hospital/Waiting_Room_Chair", "pose": [17.0, 6.0, 179.9998479605043]}, {"name": "world_waiting_chair_7", "model": "Hospital/Waiting_Room_Chair", "pose": [17.8, 6.0, 179.9998479605043]}, {"name": "world_waiting_chair_8", "model": "Hospital/Waiting_Room_Chair", "pose": [18.6, 6.0, 179.9998479605043]}, {"name": "world_waiting_chair_9", "model": "Hospital/Waiting_Room_Chair", "pose": [19.4, 6.0, 179.9998479605043]}, {"name": "world_waiting_chair_10", "model": "Hospital/Waiting_Room_Chair", "pose": [20.2, 6.0, 179.9998479605043]}, {"name": "world_waiting_chair_11", "model": "Hospital/Waiting_Room_Chair", "pose": [21.0, 6.0, 179.9998479605043]}, {"name": "world_waiting_chair_12", "model": "Hospital/Waiting_Room_Chair", "pose": [21.8, 6.0, 179.9998479605043]}, {"name": "world_waiting_chair_13", "model": "Hospital/Waiting_Room_Chair", "pose": [22.6, 6.0, 179.9998479605043]}, {"name": "world_waiting_chair_14", "model": "Hospital/Waiting_Room_Chair", "pose": [23.4, 6.0, 179.9998479605043]}, {"name": "world_waiting_bench_1", "model": "Hospital/Waiting_Room_Bench", "pose": [14.0, 3.5, 179.9998479605043]}, {"name": "world_waiting_bench_2", "model": "Hospital/Waiting_Room_Bench", "pose": [16.5, 3.5, 179.9998479605043]}, {"name": "world_waiting_bench_3", "model": "Hospital/Waiting_Room_Bench", "pose": [19.0, 3.5, 179.9998479605043]}, {"name": "world_waiting_bench_4", "model": "Hospital/Waiting_Room_Bench", "pose": [21.5, 3.5, 179.9998479605043]}, {"name": "world_waiting_drinks_machine_1", "model": "Hospital/Drinks_Machine", "pose": [12.7, 0.9, -89.99963750135457]}, {"name": "world_waiting_water_dispenser_1", "model": "Hospital/Water_Dispenser", "pose": [12.4, 9.4, 89.99963750135457]}, {"name": "world_waiting_side_table_1", "model": "Hospital/Side_Table", "pose": [16.0, 4.5, 0.0]}, {"name": "world_waiting_side_table_2", "model": "Hospital/Side_Table", "pose": [22.0, 4.5, 0.0]}, {"name": "world_waiting_trashcan_1", "model": "Hospital/Trashcan", "pose": [12.5, 1.0, 0.0]}, {"name": "world_waiting_trashcan_2", "model": "Hospital/Trashcan", "pose": [24.5, 1.0, 0.0]}, {"name": "world_waiting_mop_set_1", "model": "Hospital/Mop_Set", "pose": [24.5, 0.5, 0.0]}]}, {"name": "sub_hallway", "corners": [[12.0, 10.05], [25.0, 10.05], [25.0, 13.05], [12.0, 13.05]], "walls": [[[12.0, 13.05], [25.0, 13.05]], [[25.0, 13.05], [25.0, 10.05]], [[25.0, 10.05], [22.75, 10.05]], [[21.25, 10.05], [15.75, 10.05]], [[14.25, 10.05], [12.0, 10.05]]], "entities": []}, {"name": "operating_room", "corners": [[12.0, 13.1], [18.0, 13.1], [18.0, 21.6], [12.0, 21.6]], "walls": [[[12.0, 13.1], [12.0, 16.6]], [[12.0, 18.1], [12.0, 21.6]], [[12.0, 21.6], [18.0, 21.6]], [[18.0, 21.6], [18.0, 13.1]], [[18.0, 13.1], [12.0, 13.1]]], "entities": [{"name": "world_or_operating_table_1", "model": "Hospital/Operating_Table", "pose": [15.0, 19.0, 0.0]}, {"name": "world_or_surgical_table_1", "model": "Hospital/Surgical_Table", "pose": [15.0, 15.5, 0.0]}, {"name": "world_or_anesthesia_machine_1", "model": "Hospital/Anesthesia_Machine", "pose": [14.2, 19.0, 89.99963750135457]}, {"name": "world_or_instrument_table_1", "model": "Hospital/Instrument_Table", "pose": [15.8, 17.7, -89.99963750135457]}, {"name": "world_or_surgical_tray_1", "model": "Hospital/Surgical_Instrument_Tray", "pose": [15.8, 17.7, 0.0]}, {"name": "world_or_vital_monitor_1", "model": "Hospital/Vital_Signal_Station", "pose": [15.8, 19.0, -89.99963750135457]}, {"name": "world_or_defibrillator_1", "model": "Hospital/Defibrillator", "pose": [15.8, 17.6, 0.0]}, {"name": "world_or_ventilator_1", "model": "Hospital/Ventilator", "pose": [14.2, 15.35, 89.99963750135457]}, {"name": "world_or_medical_cabinet_1", "model": "Hospital/Medical_Cabinet", "pose": [12.7, 20.7, 89.99963750135457]}, {"name": "world_or_supply_cabinet_1", "model": "Hospital/Supply_Cabin", "pose": [17.05, 21.0, -89.99963750135457]}, {"name": "world_or_biohazard_container_1", "model": "Hospital/Biohazard_Container", "pose": [17.7, 13.7, 0.0]}, {"name": "world_or_trashcan_1", "model": "Hospital/Trashcan", "pose": [17.7, 13.3, 0.0]}]}, {"name": "laboratory", "corners": [[12.0, 21.65], [18.0, 21.65], [18.0, 30.15], [12.0, 30.15]], "walls": [[[12.0, 21.65], [12.0, 25.15]], [[12.0, 26.65], [12.0, 30.15]], [[12.0, 30.15], [18.0, 30.15]], [[18.0, 30.15], [18.0, 21.65]], [[18.0, 21.65], [12.0, 21.65]]], "entities": [{"name": "world_lab_bench_1", "model": "Hospital/Lab_Bench", "pose": [15.0, 26.65, 0.0]}, {"name": "world_lab_bench_2", "model": "Hospital/Lab_Bench", "pose": [15.0, 28.65, 0.0]}, {"name": "world_lab_microscope_1", "model": "Hospital/Microscope_Station", "pose": [14.4, 26.4, 0.0]}, {"name": "world_lab_microscope_2", "model": "Hospital/Microscope_Station", "pose": [14.4, 28.4, 0.0]}, {"name": "world_lab_stool_1", "model": "Hospital/Lab_Stool", "pose": [14.5, 25.9, 179.9998479605043]}, {"name": "world_lab_stool_2", "model": "Hospital/Lab_Stool", "pose": [14.5, 27.9, 179.9998479605043]}, {"name": "world_lab_stool_3", "model": "Hospital/Lab_Stool", "pose": [15.5, 25.9, 179.9998479605043]}, {"name": "world_lab_medical_cabinet_1", "model": "Hospital/Medical_Cabinet", "pose": [12.7, 29.2, 89.99963750135457]}, {"name": "world_lab_refrigerated_unit_1", "model": "Hospital/Refrigerated_Medicine_Unit", "pose": [17.5, 29.65, -90.13687849338227]}, {"name": "world_lab_shelf_1", "model": "Hospital/Shelf", "pose": [12.5, 28.5, 89.99963750135457]}, {"name": "world_lab_shelf_2", "model": "Hospital/Shelf", "pose": [17.5, 28.5, -90.13687849338227]}, {"name": "world_lab_biohazard_container_1", "model": "Hospital/Biohazard_Container", "pose": [16.0, 26.5, 0.0]}, {"name": "world_lab_biohazard_container_2", "model": "Hospital/Biohazard_Container", "pose": [16.0, 28.5, 0.0]}, {"name": "world_lab_autoclave_1", "model": "Hospital/Autoclave", "pose": [17.5, 27.5, -89.99963750135457]}, {"name": "world_lab_trashcan_1", "model": "Hospital/Trashcan", "pose": [16.0, 26.1, 0.0]}, {"name": "world_lab_trashcan_2", "model": "Hospital/Trashcan", "pose": [16.0, 28.1, 0.0]}]}]}. You MUST follow the Universal Spatial Reasoning Protocol (USRP) when producing all positions, movement directions, and yaw angles. Use these behavior tree nodes only: Node name: AdvanceQueue
Purpose: Commands multiple agents to form a queue and then advance progressively toward the front. Each agent first moves to its designated waiting position, then successively moves to the previous agent's position as the queue advances. The order of the queue is determined by the order in which agents are listed.
Inputs:
	- agents_names (list[string]): List of participating agent names in queue order. For example: ["hunav_1", "hunav_2", "hunav_3"]. This order determines the queue progression.
	- wait_duration (double): Base waiting time [s] applied each time an agent reaches a queue position. This pause allows the queue to progress gradually.
	- front_agent_pose (list[double]): The pose ([x, y, yaw]) of the first agent at the front of the queue. Positions for the remaining agents are computed automatically based on this pose, direction, and distance.
	- direction (double): Yaw angle defining the direction in which the queue extends. All waiting positions are generated along this direction.
	- distance (double): Nominal spacing between consecutive agents in the queue.
Outputs:
Metadata:
	-Category: Action node
	-Node type: multi agent node

Node name: FormQueue
Purpose: Commands agents to queue in line, the order of agents is determined by the order of their names in the list.
Inputs:
	- agents_names (list[string]): List of participating agent names. Must be passed as a list of string, e.g. ["hunav_1", "hunav_2"]
	- wait_duration (list[double]): Durations for which each agent should wait [s].
	- front_agent_pose (list[double]): The pose ([x, y, yaw]) of the agent in the front of the queue, the pose of agents behind will be calculated base on this agent's pose and queue direction.
	- direction (double): The direction of the queue line given in yaw angle, the pose of agents will be calculated base on this attribute and front agent's pose.
	- distance (double): Nominal spacing between consecutive agents in the queue.
Outputs:
Metadata:
	-Category: Action node
	-Node type: multi agent node

Node name: ConversationFormation
Purpose: Manages the formation of a conversation among multiple agents.
Inputs:
	- main_agent_name (int): Identifier of the primary agent leading the conversation.
	- conversation_duration (double): Total duration of the conversation [s].
	- target_x (double): X-Coordinate of where conversation's central point will take place.
	- target_y (double): Y-Coordinate of where conversation's central point will take place.
	- time_step (double): Time step for movement updates [s].
	- non_main_agent_names (string): List of participating agent names. Must be passed as a list of string, e.g. ["hunav_1", "hunav_2"]
Outputs:
Metadata:
	-Category: Action node
	-Node type: single agent node

Node name: GroupWalk
Purpose: Directs a group to walk together with a designated main agent.
Inputs:
	- main_agent_name (int): Identifier of the main agent guiding the group.
	- time_step (double): Time increment used for updating movement [s].
	- non_main_agent_names (string): List of the non-main agents' names. Must be passed as a list of string, e.g. ["hunav_1", "hunav_2"]
	- duration (double): Duration for which the behaviour runs [s]. If omitted, the behaviour runs indefinitely.
Outputs:
Metadata:
	-Category: Action node
	-Node type: single agent node

Node name: FollowAgent
Purpose: Commands an agent to follow another target agent.
Inputs:
	- agent_name (int): Identifier of the follower agent.
	- time_step (double): Time step for movement updates [s].
	- target_agent_name (int): Identifier of the agent to be followed.
	- duration (double): Duration for which the behaviour is active [s]. If omitted, the behaviour runs indefinitely.
Outputs:
Metadata:
	-Category: Action node
	-Node type: single agent node

Node name: ApproachAgent
Purpose: Directs the agent to move towards another agent for a defined duration.
Inputs:
	- agent_name (int): Identifier of the approaching agent.
	- target_agent_name (int): Identifier of the target agent.
	- time_step (double): Time step for movement updates [s].
	- duration (double): Duration of the approach action [s].
Outputs:
Metadata:
	-Category: Action node
	-Node type: single agent node

Node name: TimeDelayDecorator
Purpose: Delays the execution of its child node by a specified amount of time. Returns FAILURE until delay elapses, then ticks child.
Inputs:
	- delay (double): Delay time before the child node is ticked [s].
Outputs:
Metadata:
	-Category: Decorator node
	-Node type: single agent node

Node name: GoTo
Purpose: Commands the agent to navigate directly to a specified point.
Inputs:
	- agent_name (int): Name of the agent.
	- time_step (double): Time step for movement updates [s].
	- target_x (double): X-Coordinate of the target goal position.
	- target_y (double): Y-Coordinate of the target goal position.
	- tolerance (double): Distance to consider 'at goal' [m].
Outputs:
Metadata:
	-Category: Action node
	-Node type: single agent node

Node name: StopAndWaitTimerAction
Purpose: Implements a stop-and-wait behaviour that stops the agent for a defined duration.
Inputs:
	- agent_name (int): Identifier of the agent.
	- wait_duration (double): Duration for which the agent should wait [s].
Outputs:
Metadata:
	-Category: Action node
	-Node type: single agent node

Node name: FindNearestAgent
Purpose: Identifies the nearest agent relative to a given agent.
Inputs:
	- agent_name (int): Identifier of the querying agent.
Outputs:
	- target_agent_name (int): Identifier of the nearest agent found.
Metadata:
	-Category: Action node
	-Node type: single agent node. Only return valid JSON using the format declared in the system context, with no explanation, thoughts, or extra text.

    Example output:
    ```json
{
  "hunav_agents": [
    {
      "name": "hunav_1",
      "pos": [8.5, 2.0, 90.0],
      "type": "adult",
      "model": "male_adult_construction_01",
    },
    {
      "name": "hunav_2",
      "pos": [8.5, 3.0, 90.0],
      "type": "adult",
      "model": "male_adult_construction_02",
    },
    {
      "name": "hunav_3",
      "pos": [8.5, 4.0, 90.0],
      "type": "adult",
      "model": "male_adult_construction_03",
    },
    {
      "name": "hunav_4",
      "pos": [8.5, 5.0, 90.0],
      "type": "adult",
      "model": "male_adult_construction_05",
    },
    {
      "name": "hunav_5",
      "pos": [8.5, 6.0, 90.0],
      "type": "adult",
      "model": "male_adult_construction_01",
    }
  ],

  "single_agent_nodes": [
    {
      "name": "GoTo",
      "attributes": {
        "agent_name": "hunav_1",
        "target_x": 4.0,
        "target_y": 1.0,
        "tolerance": 0.5
      },
      "order": 1
    },
    {
      "name": "GoTo",
      "attributes": {
        "agent_name": "hunav_1",
        "target_x": 14.0,
        "target_y": 2.0,
        "tolerance": 0.5
      },
      "order": 2
    },
    {
      "name": "GoTo",
      "attributes": {
        "agent_name": "hunav_2",
        "target_x": 4.0,
        "target_y": 1.0,
        "tolerance": 0.5
      },
      "order": 1
    },
    {
      "name": "GoTo",
      "attributes": {
        "agent_name": "hunav_2",
        "target_x": 14.0,
        "target_y": 2.0,
        "tolerance": 0.5
      },
      "order": 2
    },
    {
      "name": "GoTo",
      "attributes": {
        "agent_name": "hunav_3",
        "target_x": 4.0,
        "target_y": 1.0,
        "tolerance": 0.5
      },
      "order": 1
    },
    {
      "name": "GoTo",
      "attributes": {
        "agent_name": "hunav_3",
        "target_x": 14.0,
        "target_y": 2.0,
        "tolerance": 0.5
      },
      "order": 2
    },
    {
      "name": "GoTo",
      "attributes": {
        "agent_name": "hunav_4",
        "target_x": 4.0,
        "target_y": 1.0,
        "tolerance": 0.5
      },
      "order": 1
    },
    {
      "name": "GoTo",
      "attributes": {
        "agent_name": "hunav_4",
        "target_x": 14.0,
        "target_y": 2.0,
        "tolerance": 0.5
      },
      "order": 2
    },
    {
      "name": "GoTo",
      "attributes": {
        "agent_name": "hunav_5",
        "target_x": 4.0,
        "target_y": 1.0,
        "tolerance": 0.5
      },
      "order": 1
    },
    {
      "name": "GoTo",
      "attributes": {
        "agent_name": "hunav_5",
        "target_x": 14.0,
        "target_y": 2.0,
        "tolerance": 0.5
      },
      "order": 2
    }
  ],

  "multi_agent_nodes": [
    {
      "name": "AdvanceQueue",
      "attributes": {
        "agents_names": [
          "hunav_1",
          "hunav_2",
          "hunav_3",
          "hunav_4",
          "hunav_5"
        ],
        "wait_duration": 20.0,
        "front_agent_pose": [
          8.5,
          2.0,
          90.0
        ],
        "direction": 90.0,
        "distance": 1.0
      },
      "orders": {
        "hunav_1": 0,
        "hunav_2": 0,
        "hunav_3": 0,
        "hunav_4": 0,
        "hunav_5": 0
      }
    }
  ]
}
    ```
"""

BEHAVIOR_TREE_FIELD_DESCRIPTION = """
    Top-level structure
    - "hunav_agents" contains a list of hunav agents, each with:
      - `name`: the agent's unique identifier (e.g., "hunav_1").
      - `pos`: a list [x, y, yaw] representing the object's position and rotation. You should pay attention to where the agent should be spawned and faced, place the agent within the correct zone and adjust the yaw reasonably.
      - `type`: the type of dynamic obstacle (e.g., `adult`, `child`, etc.).
      - `model`: the type of model used for the dynamic obstacle. the type of model can be one of the following only:
        - "female_adult_business_02"
        - "female_adult_medical_01"
        - "female_adult_police_01"
        - "female_adult_police_02"
        - "female_adult_police_03"
        - "male_adult_construction_01"
        - "male_adult_construction_02"
        - "male_adult_construction_03"
        - "male_adult_construction_05"
        - "male_adult_medical_01"
        - "male_adult_police_04"

    - "single_agent_nodes": Contains a list of behavior tree nodes that one and only one agent involved in, each has:
      - `name`: name of the node, only use provided node name, do not modify!
      - `attributes`: a dictionary of key-value pairs (parameters passed to the node)
      - `order`: an integer represent the order of execution of this node in the agent behavior tree. The agent will handle nodes in a ascending order determined by this field. For each agent, every nodes must be unique no matter the type (single-agent or multi-agent nodes) is.

    - "multi_agent_nodes": Contains a list of behavior tree nodes that more than one agent involved in, each has:
      - `name`: name of the node
      - `attributes`: a dictionary of key-value pairs (parameters passed to the node)
      - `order`: a dictionary of key-value pairs (<agent name>-<order value>) represent the order of execution of this node in each agent behavior tree. The agents will handle nodes in a ascending order determined by this field. For each agent, every nodes must be unique no matter the type (single-agent or multi-agent nodes) is.
"""

SYSTEM_INSTRUCTION = f"""
{ROLE}
{REASONING_GUIDE}
{WORLD_DESCRIPTION}
"""

ARENA_FORMAT = f"""
{ARENA_OUTPUT_FORMAT}
{ARENA_FIELD_DESCRIPTION}
"""

BEHAVIOR_TREE_FORMAT = f"""
{BEHAVIOR_TREE_OUTPUT_FORMAT}
{BEHAVIOR_TREE_FIELD_DESCRIPTION}
"""

SPLIT_PROMPT_INSTRUCTION = """
Your task is split user prompt into 2 prompts for 2 human simulator pipeline.
One is Ambient Agents pipeline, which will control how group of pedestrians navigate, your prompt will affect the navigation direction of the pedestrian groups, where the pedestrians groups is spawned, and where the groups will start and finish. Your prompt should describes the sequence of places the pedestrian groups should follow, but don't make up places, only use places the user refers if mentioned.
The other pipeline is Spotlight Agent pipeline, which should be more detailed as this pipeline can control complex behavior of agents.

Do NOT explain anything. Output JSON only, and must strictly follow this structure:
```json
{
    "ambient_agents_prompt": <ambient_agents_prompt>,
    "spotlight_agents_prompt": <spotlight_agents_prompt>
}
```

Example:
Input: Depict an emergency evacuation where at first, there're 5 people waiting in line by the pharmacy room door, gradually advance to move forward, then a fire occurs and everyone in every rooms run out of their room, to the hallways, then toward the exit in the main hallways.
Output:
```json
{
    "ambient_agents_prompt": "People run out of their room, to the hallways, and through the main hallway entrance.",
    "spotlight_agents_prompt": "A group of 5 peopel stand into a queue in the main central hallway, by the pharmacy room door, every one should stand 1 meter away from the wall, and the first of the line should stand one meter away from the edge of the door. As soon as a spot opens at the front, each person immediately steps forward, advancing in sequence toward the waiting area door. Every person, when they reach the front of the line, must wait 20 seconds and then enter the pharmacy room, then he enters the pharmacy room."
}
```
"""
