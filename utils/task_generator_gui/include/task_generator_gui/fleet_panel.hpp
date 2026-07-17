#ifndef TASK_GENERATOR_GUI_FLEET_PANEL_HPP
#define TASK_GENERATOR_GUI_FLEET_PANEL_HPP

#include "rclcpp/rclcpp.hpp"

#include <rviz_common/panel.hpp>
#include <rviz_common/ros_integration/ros_node_abstraction_iface.hpp>

#include "task_generator_msgs/srv/query_robots.hpp"
#include "task_generator_msgs/srv/spawn_robot.hpp"
#include "task_generator_msgs/srv/despawn_robot.hpp"
#include "task_generator_msgs/msg/robot_fleet.hpp"
#include "task_generator_msgs/msg/robot_queue.hpp"

#include <QComboBox>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QSignalBlocker>
#include <QVBoxLayout>

#include <chrono>
#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace task_generator_gui
{

class FleetPanel : public rviz_common::Panel
{
    Q_OBJECT

public:
    explicit FleetPanel(QWidget* parent = nullptr);
    ~FleetPanel() override;

    void onInitialize() override;
    void load(const rviz_common::Config& config) override;

    void whenReady(std::function<bool()> ready_check,
                   std::function<void()> action,
                   std::chrono::milliseconds period = std::chrono::milliseconds(200));

protected:
    std::shared_ptr<rviz_common::ros_integration::RosNodeAbstractionIface> node_ptr;
    rclcpp::Node::SharedPtr node;

    std::string task_generator_node;

    rclcpp::Client<task_generator_msgs::srv::QueryRobots>::SharedPtr query_robots_client;
    rclcpp::Client<task_generator_msgs::srv::SpawnRobot>::SharedPtr spawn_robot_client;
    rclcpp::Client<task_generator_msgs::srv::DespawnRobot>::SharedPtr despawn_robot_client;

    rclcpp::Subscription<task_generator_msgs::msg::RobotFleet>::SharedPtr robot_fleet_sub;
    rclcpp::Subscription<task_generator_msgs::msg::RobotQueue>::SharedPtr robot_queue_sub;

    task_generator_msgs::msg::RobotFleet::SharedPtr last_fleet;
    task_generator_msgs::msg::RobotQueue::SharedPtr last_pending;

    std::string selected_robot_model;
    std::vector<std::string> robot_models;

    QComboBox*   robot_combobox{nullptr};
    QPushButton* spawn_robot_button{nullptr};
    QGroupBox*   fleet_group{nullptr};
    QVBoxLayout* fleet_layout{nullptr};
    QGroupBox*   queue_group{nullptr};
    QVBoxLayout* queue_layout{nullptr};

    void setupUi();
    void rebuildFleet();
    void rebuildQueue();
    void sendDespawn(const std::string& name);

private Q_SLOTS:
    void onRobotChanged(const QString& text);
    void spawnRobotButtonActivated();
};

} // namespace task_generator_gui

#endif // TASK_GENERATOR_GUI_FLEET_PANEL_HPP
