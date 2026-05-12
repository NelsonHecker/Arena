# One pedestrian to spawn, paired with its backend-interpreted asset reference.
# model_ref is backend-interpreted:
#   Gazebo: absolute SDF path, OR inline SDF XML (detected by leading '<').
#   Isaac:  character name (key into Person asset dict).
arena_people_msgs/Pedestrian pedestrian
string                       model_ref
