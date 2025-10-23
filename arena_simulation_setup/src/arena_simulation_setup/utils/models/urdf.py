import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import attrs

from . import Model, ModelProvider, ModelType


class ModelProvider_URDF(ModelProvider.provides(ModelType.URDF)):

    @classmethod
    def load(cls, model_dir, model, loader_args):

        if loader_args is None:
            loader_args = {}

        base_path = model_dir / "urdf"
        xacro_path = base_path / f"{model}.urdf.xacro"
        model_path = base_path / f"{model}.urdf"

        if not xacro_path.is_file():
            return None

        def to_string(v: Any) -> str:
            if attrs.has(type(v)):
                v = repr(attrs.asdict(v))
            if isinstance(v, dict):
                return repr(json.dumps(v))
            return repr(str(v))
        try:

            model_desc = subprocess.check_output([
                "ros2",
                "run",
                "xacro",
                "xacro",
                str(xacro_path),
                *(
                    f"{k}:={to_string(v)}"
                    for k, v
                    in loader_args.items()
                    if v is not None
                ),
            ]).decode("utf-8")

            with open(model_path, 'w') as f:
                f.write(model_desc)

            base_dir = os.path.dirname(model_path)
            tree = ET.parse(model_path)
            root = tree.getroot()

            prefix = "package://jackal_description"

            # Iterate over every element in the XML tree and update 'filename' attributes
            for elem in root.iter():
                if 'filename' in elem.attrib:
                    original_path = elem.attrib['filename']
                    # Remove the specific package prefix if present
                    if original_path.startswith(prefix):
                        # Remove the prefix and any leading '/'
                        new_relative = original_path[len(prefix):].lstrip('/')
                        original_path = new_relative
                        print(f"Removed prefix: {prefix} -> New relative path: {original_path}")
                    # Convert to absolute path if it's not already
                    if not os.path.isabs(original_path):
                        abs_path = os.path.abspath(os.path.join(base_dir, original_path))
                        elem.attrib['filename'] = abs_path
                        print(f"Updated relative path to absolute: {original_path} -> {abs_path}")

            # Write the updated XML tree to a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".urdf", mode="wb") as tmp:
                tree.write(tmp, encoding="utf-8", xml_declaration=True)
                temp_filepath = tmp.name
                print(f"Converted URDF saved to temporary file: {temp_filepath}")

            return Model(
                type=ModelType.URDF,
                name=model,
                description=model_desc,
                path=Path(temp_filepath)
            )

        except subprocess.CalledProcessError as e:
            print(
                f"error processing model {model} URDF file {xacro_path}. refusing to load.\n{e}\n{e.output.decode('utf-8')}",
                file=sys.stderr
            )
            raise
            return None
