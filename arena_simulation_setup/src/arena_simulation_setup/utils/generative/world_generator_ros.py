import sys

import std_srvs.srv
from arena_rclpy_mixins.ROSParamServer import ROSParamServer
from arena_rclpy_mixins.ServiceNamespace import ServiceNamespace

from arena_simulation_setup.tree.World.World import WorldDescription, WorldIdentifier

from .schema import declare_config_params
from .world_generator import WorldGenerator, WorldGeneratorType


class WorldGeneratorROS(WorldGenerator, ROSParamServer, ServiceNamespace):
    def _get_parameters(self) -> tuple[WorldGeneratorType, dict, int]:
        name = WorldGeneratorType(self.get_parameter('generator').value)
        seed = self.get_parameter('seed').value
        prefix = f'algorithm.{name.value}'
        raw = self.get_parameters_by_prefix(prefix)
        config = {leaf: param.value for leaf, param in raw.items()}

        self.get_logger().info(f'world generator: "{name}"')
        self.get_logger().info(f'config: {config}')
        self.get_logger().info(f'seed: {seed}')

        return name, config, seed

    def _cb_generate(self, request: std_srvs.srv.Trigger.Request, response: std_srvs.srv.Trigger.Response) -> std_srvs.srv.Trigger.Response:
        try:
            self.update_generator(*self._get_parameters())
            WorldIdentifier(self.get_parameter('world').value).resolve_sync().save(WorldDescription.from_levels(self.compute()))
            response.success = True
        except Exception as e:
            response.success = False
            response.message = repr(e)
            self.get_logger().error(f"Failed to generate world: {repr(e)}")

        return response

    def __init__(self):
        ROSParamServer.__init__(self, 'world_generator')

        self.declare_parameter('generator', WorldGeneratorType.HALLWAY.value)
        self.declare_parameter('seed', -1)
        self.declare_parameter('world', 'generated')

        for gen_type in WorldGenerator.available():
            model_cls = WorldGenerator.config_model(gen_type)
            declare_config_params(self, f'algorithm.{gen_type.value}', model_cls)

        WorldGenerator.__init__(self, *self._get_parameters())

        self.set_up_services()
        self.get_logger().info('initialized')

    def set_up_services(self):
        self.create_service(std_srvs.srv.Trigger, self.service_namespace('generate_world'), self._cb_generate)


def main(argv: list[str] = sys.argv) -> None:
    import os

    import rclpy
    import rclpy.utilities
    from arena_rclpy_mixins.spin import spin_node

    rclpy.init(args=argv)
    argv = rclpy.utilities.remove_ros_args(argv)

    if len(argv) > 1:
        print(f'usage: {os.path.basename(__file__)}')
        sys.exit(1)

    spin_node(WorldGeneratorROS())


if __name__ == '__main__':
    main()
