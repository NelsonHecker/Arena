# Streaming camera keyframe, expressed in the current viewport reference frame.
builtin_interfaces/Time target_time  # wall time this pose should be reached (interpolation buffer)
geometry_msgs/Pose pose  # camera pose in the reference frame
bool world_orientation   # true keeps the aim world-stable, false rotates it with the reference
float64 fov              # horizontal field of view, radians; <= 0 leaves it unchanged
