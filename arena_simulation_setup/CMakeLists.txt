cmake_minimum_required(VERSION 3.8)
project(arena_simulation_setup)

# Default to C++14
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 14)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)

include_directories(
  ${rclcpp_INCLUDE_DIRS}
  ${geometry_msgs_INCLUDE_DIRS}
  ${tf2_ros_INCLUDE_DIRS}
  ${tf2_geometry_msgs_INCLUDE_DIRS}
)

# Add executable
add_executable(pose_to_tf scripts/pose_to_tf.cpp)
ament_target_dependencies(pose_to_tf rclcpp geometry_msgs tf2_ros tf2_geometry_msgs)

# Install target
install(TARGETS pose_to_tf
  DESTINATION lib/${PROJECT_NAME})

# Install launch files
install(
  DIRECTORY launch
  DESTINATION share/${PROJECT_NAME}/launch
)

# Install configurations
install(
  DIRECTORY configs
  DESTINATION share/${PROJECT_NAME}/configs
)

ament_python_setup()
ament_package()