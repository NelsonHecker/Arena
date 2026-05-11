cmake_minimum_required(VERSION 3.5)
project(arena_runtime_msgs)

find_package(ament_cmake_auto REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(rcl_interfaces REQUIRED)

ament_auto_find_build_dependencies()

file(GLOB MSG_FILES RELATIVE ${CMAKE_CURRENT_SOURCE_DIR} "msg/*.msg")
file(GLOB SRV_FILES RELATIVE ${CMAKE_CURRENT_SOURCE_DIR} "srv/*.srv")
file(GLOB ACTION_FILES RELATIVE ${CMAKE_CURRENT_SOURCE_DIR} "action/*.action")

rosidl_generate_interfaces(${PROJECT_NAME}
  ${MSG_FILES}
  ${SRV_FILES}
  ${ACTION_FILES}
  DEPENDENCIES std_msgs geometry_msgs builtin_interfaces rcl_interfaces
)


ament_export_dependencies(rosidl_default_runtime)
ament_auto_package()