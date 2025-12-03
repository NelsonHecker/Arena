import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import attrs

from arena_simulation_setup import AB_DIR
from arena_simulation_setup.tree import Identifier, ResolverBase


def _get_attrib(
    element: ET.Element,
    attribute: str,
    default: Optional[str] = None
) -> str:
    val = element.get(attribute)
    if val is not None:
        return str(val)

    sub_elem = element.find(attribute)
    if sub_elem is not None:
        return str(sub_elem.text)

    if default is not None:
        return default

    raise ValueError(f"attribute {attribute} not found in {element}")


@attrs.define()
class ParametrizedConfig:
    @attrs.define()
    class ObstacleConfig:
        min: int
        max: int
        type: str
        model: str

    STATIC: list[ObstacleConfig]
    INTERACTIVE: list[ObstacleConfig]
    DYNAMIC: list[ObstacleConfig]


class ParametrizedResolver(ResolverBase):
    base_path = AB_DIR / 'configs' / 'parametrized'

    async def resolve(self, identifier):
        target_path = (self.base_path / f'{identifier.name}').with_suffix('.xml')
        if target_path.exists():
            return target_path
        return None

    def listall(self, **kwargs):
        if not self.base_path.is_dir():
            yield from ()
        yield from (
            self._IdentifierT(entry.relative_to(self.base_path).with_suffix('').as_posix())
            for entry
            in self.base_path.glob('**/*.xml')
            if entry.is_file()
        )


class ParametrizedIdentifier(Identifier[ParametrizedConfig]):
    def load(self, path: Path, /, **kwargs) -> ParametrizedConfig:
        del kwargs

        tree = ET.parse(path)
        root = tree.getroot()

        assert isinstance(
            root, ET.Element) and root.tag == "random", "not a random.xml desc"

        def xml_to_config(config) -> ParametrizedConfig.ObstacleConfig:
            return ParametrizedConfig.ObstacleConfig(
                min=int(_get_attrib(config, "min")),
                max=int(_get_attrib(config, "max")),
                type=_get_attrib(config, "type", ""),
                model=_get_attrib(config, "model")
            )

        return ParametrizedConfig(
            STATIC=list(map(xml_to_config, root.findall("./static/obstacle") or [])),
            INTERACTIVE=list(map(xml_to_config, root.findall("./static/interactive") or [])),
            DYNAMIC=list(map(xml_to_config, root.findall("./static/dynamic") or [])),
        )


ParametrizedIdentifier.use(ParametrizedResolver(ParametrizedIdentifier))
