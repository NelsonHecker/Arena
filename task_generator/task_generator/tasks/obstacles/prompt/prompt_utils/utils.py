import json
from arena_simulation_setup.tree.World import WorldDescription


def get_world_metatdata(world_description: WorldDescription) -> str:
    """
    Get Zones name, description, doors names and other entities

    Args:
        world_description : WorldDescription
            The world description to preprocess.

    Returns:
        parsed : str
            The preprocessed JSON.
    """
    parsed = {}

    parsed["zones"] = []
    for zone in world_description.zones:
        parsed_zone = {
            "name": zone.name,
            "doors": [door.name for door in zone.doors],
            "entities": [entity.name for entity in zone.entities.static],
        }
        parsed["zones"].append(parsed_zone)

    return json.dumps(parsed)


def get_world_detail_info(
    world_description: WorldDescription, zones_names: list[str]
) -> str:
    parsed = {}

    parsed["zones"] = []
    for zone in world_description.zones:
        if zone.name in zones_names:
            zones_names.remove(zone.name)

            parsed_zone = {
                "name": zone.name,
                "doors": [
                    {
                        "start": [door.start.x, door.start.y],
                        "end": [door.end.x, door.end.y],
                    }
                    for door in zone.doors
                ],
                "entities": [
                    {
                        "name": entity.name,
                        "pos": [entity.pose.position.x, entity.pose.position.y],
                    }
                    for entity in zone.entities.static
                ],
            }

            parsed["zones"].append(parsed_zone)
        else:
            continue

    return json.dumps(parsed)
