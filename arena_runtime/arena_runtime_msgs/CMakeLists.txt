cmake_minimum_required(VERSION 3.5)
project(arena_runtime_msgs)

find_package(ament_cmake_auto REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(rcl_interfaces REQUIRED)

ament_auto_find_build_dependencies()

rosidl_generate_interfaces(${PROJECT_NAME}
  msg/EnvRecord.msg
  msg/EnvRegistry.msg
  msg/Heartbeat.msg
  msg/HoldEntry.msg
  msg/HoldRegistry.msg
  msg/ShutdownRequest.msg
  msg/ViewportView.msg
  msg/WorldExtent.msg
  srv/CleanupEnv.srv
  srv/ConfirmWorld.srv
  srv/DespawnEnv.srv
  srv/LifecycleHold.srv
  srv/LifecycleUnpauseWindow.srv
  srv/RegisterEnv.srv
  srv/SpawnEnv.srv
  srv/ViewportSetProjection.srv
  srv/ViewportSetReferenceFrame.srv
  srv/ViewportSetView.srv
  DEPENDENCIES std_msgs geometry_msgs builtin_interfaces rcl_interfaces
)


ament_export_dependencies(rosidl_default_runtime)
ament_auto_package()