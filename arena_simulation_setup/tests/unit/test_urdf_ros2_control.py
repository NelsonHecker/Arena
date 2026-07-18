from __future__ import annotations

import xml.etree.ElementTree as ET

from arena_simulation_setup.utils.models.urdf import _lock_passive_joints, _strip_unregistered_ros2_control

URDF = """
<robot name="x">
  <ros2_control name="chassis" type="system">
    <hardware><plugin>gz_ros2_control/GazeboSimSystem</plugin></hardware>
  </ros2_control>
  <ros2_control name="left_wheel_controller" type="system">
    <hardware><plugin>gazebo_ros2_control/GazeboSystem</plugin></hardware>
  </ros2_control>
  <ros2_control name="arm" type="system">
    <hardware><plugin>ur_robot_driver/URPositionHardwareInterface</plugin></hardware>
  </ros2_control>
  <ros2_control name="broken" type="system">
    <hardware/>
  </ros2_control>
  <gazebo>
    <plugin filename="libgazebo_ros2_control.so" name="gazebo_ros2_control">
      <parameters>/opt/ros/jazzy/share/irobot_create_control/config/control.yaml</parameters>
    </plugin>
  </gazebo>
  <gazebo reference="imu_joint">
    <preserveFixedJoint>true</preserveFixedJoint>
  </gazebo>
</robot>
"""

REGISTERED = frozenset({"ur_robot_driver/URPositionHardwareInterface"})


def test_strips_unregistered_keeps_registered_and_sentinel():
    root = ET.fromstring(URDF)
    _strip_unregistered_ros2_control(root, REGISTERED)
    names = [el.attrib["name"] for el in root.findall("ros2_control")]
    assert names == ["chassis", "arm"]


def test_classic_gazebo_host_plugin_removed_with_empty_wrapper():
    root = ET.fromstring(URDF)
    _strip_unregistered_ros2_control(root, REGISTERED)
    plugins = [p for g in root.findall("gazebo") for p in g.findall("plugin")]
    assert not plugins
    assert root.find("gazebo/preserveFixedJoint") is not None


def test_empty_registered_set_is_noop():
    root = ET.fromstring(URDF)
    _strip_unregistered_ros2_control(root, frozenset())
    assert len(root.findall("ros2_control")) == 4
    assert root.find("gazebo/plugin") is not None


JOINTS_URDF = """
<robot name="x">
  <joint name="wheel_drop_left_joint" type="prismatic">
    <parent link="base_link"/>
    <child link="wheel_drop_left"/>
    <axis xyz="0 1 0"/>
    <limit effort="0" lower="0" upper="0.03" velocity="0"/>
    <dynamics damping="50" friction="0.1"/>
  </joint>
  <joint name="left_wheel_joint" type="continuous">
    <parent link="base_link"/>
    <child link="left_wheel"/>
    <axis xyz="0 1 0"/>
  </joint>
  <joint name="arm_joint" type="revolute">
    <parent link="base_link"/>
    <child link="arm"/>
    <axis xyz="0 0 1"/>
    <limit effort="10" lower="-1" upper="1" velocity="1"/>
  </joint>
</robot>
"""


def test_zero_effort_joint_locked_others_untouched():
    root = ET.fromstring(JOINTS_URDF)
    _lock_passive_joints(root)
    drop = root.find("joint[@name='wheel_drop_left_joint']")
    assert drop.attrib["type"] == "fixed"
    assert drop.find("axis") is None
    assert drop.find("limit") is None
    assert drop.find("dynamics") is None
    assert drop.find("parent") is not None
    assert root.find("joint[@name='left_wheel_joint']").attrib["type"] == "continuous"
    assert root.find("joint[@name='arm_joint']").attrib["type"] == "revolute"
