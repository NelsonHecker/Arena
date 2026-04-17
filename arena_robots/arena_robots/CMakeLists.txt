cmake_minimum_required(VERSION 3.5)
project(arena_robots)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

file(GLOB _robot_dirs RELATIVE ${CMAKE_CURRENT_SOURCE_DIR}/robots
     ${CMAKE_CURRENT_SOURCE_DIR}/robots/*)
foreach(_robot IN LISTS _robot_dirs)
  set(_src ${CMAKE_CURRENT_SOURCE_DIR}/robots/${_robot})
  if(IS_DIRECTORY ${_src})
    file(GLOB _contents ${_src}/*)
    if(_contents)
      install(DIRECTORY ${_src}
              DESTINATION share/${PROJECT_NAME}/robots)
    endif()
  endif()
endforeach()

install(
  DIRECTORY config/
  DESTINATION share/${PROJECT_NAME}/config
)

install(
  DIRECTORY launch/
  DESTINATION share/${PROJECT_NAME}/launch
)

ament_python_install_package(${PROJECT_NAME})

ament_package()