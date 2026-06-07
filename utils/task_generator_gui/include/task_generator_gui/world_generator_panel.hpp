#ifndef TASK_GENERATOR_GUI_WORLD_GENERATOR_PANEL_HPP
#define TASK_GENERATOR_GUI_WORLD_GENERATOR_PANEL_HPP

#include "rclcpp/rclcpp.hpp"
#include "rclcpp/parameter_client.hpp"

#include <rviz_common/panel.hpp>
#include <rviz_common/ros_integration/ros_node_abstraction_iface.hpp>

#include "std_srvs/srv/trigger.hpp"
#include "task_generator_msgs/srv/queue_episode.hpp"
#include "task_generator_msgs/srv/reset_episode.hpp"

#include <rcl_interfaces/msg/parameter.hpp>

#include "task_generator_gui/utils/dynamic_param_tree.hpp"

#include <QComboBox>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QSignalBlocker>
#include <QSpinBox>
#include <QTreeWidget>
#include <QVBoxLayout>

#include <climits>
#include <memory>
#include <set>
#include <string>
#include <unordered_map>

namespace task_generator_gui
{

class WorldGeneratorPanel : public rviz_common::Panel
{
    Q_OBJECT

public:
    explicit WorldGeneratorPanel(QWidget* parent = nullptr);
    ~WorldGeneratorPanel() override;

    void onInitialize() override;
    void load(const rviz_common::Config& config) override;

protected:
    std::shared_ptr<rviz_common::ros_integration::RosNodeAbstractionIface> node_ptr;
    rclcpp::Node::SharedPtr node;

    std::string world_generator_node;
    std::string task_generator_node;

    std::shared_ptr<rclcpp::AsyncParametersClient> params_client_;
    rclcpp::Client<std_srvs::srv::Trigger>::SharedPtr generate_client_;
    rclcpp::Client<task_generator_msgs::srv::QueueEpisode>::SharedPtr queue_episode_client_;
    rclcpp::Client<task_generator_msgs::srv::ResetEpisode>::SharedPtr reset_episode_client_;

    QComboBox*   algorithm_combobox_;
    QLineEdit*   world_name_edit_;
    QSpinBox*    seed_spin_;
    QTreeWidget* param_tree_;
    QPushButton* generate_button_;
    QLabel*      status_label_;

    std::unordered_map<std::string, QWidget*> param_widgets_;
    std::unordered_map<std::string, uint8_t>  param_types_;

    std::unique_ptr<DynamicParamTree> param_tree_engine_;

    void setupUi();
    void loadAlgorithms();

private Q_SLOTS:
    void onAlgorithmChanged(const QString& text);
    void onGenerateClicked();
};

} // namespace task_generator_gui

#endif // TASK_GENERATOR_GUI_WORLD_GENERATOR_PANEL_HPP
