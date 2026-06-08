#include "task_generator_gui/task_generator_panel.hpp"

#include <cctype>

namespace task_generator_gui
{

void TaskGeneratorPanel::fetchCatalog(
    const std::string &catalog_name,
    std::function<void(std::vector<std::string>)> callback)
{
    if (catalog_name == "objects")
    {
        query_static_obstacles_client->async_send_request(
            std::make_shared<task_generator_msgs::srv::QueryStaticObstacles::Request>(),
            [cb = std::move(callback)](rclcpp::Client<task_generator_msgs::srv::QueryStaticObstacles>::SharedFuture f)
            {
                auto resp = f.get();
                cb(resp ? resp->ids : std::vector<std::string>{});
            });
    }
    else if (catalog_name == "pedestrians")
    {
        query_dynamic_obstacles_client->async_send_request(
            std::make_shared<task_generator_msgs::srv::QueryDynamicObstacles::Request>(),
            [cb = std::move(callback)](rclcpp::Client<task_generator_msgs::srv::QueryDynamicObstacles>::SharedFuture f)
            {
                auto resp = f.get();
                cb(resp ? resp->ids : std::vector<std::string>{});
            });
    }
    else if (catalog_name == "scenarios")
    {
        auto req   = std::make_shared<task_generator_msgs::srv::QueryScenarios::Request>();
        req->world = staged_world;
        query_scenarios_client->async_send_request(
            req,
            [cb = std::move(callback)](rclcpp::Client<task_generator_msgs::srv::QueryScenarios>::SharedFuture f)
            {
                auto resp = f.get();
                cb(resp ? resp->ids : std::vector<std::string>{});
            });
    }
    else if (catalog_name == "parametrizeds")
    {
        query_parametrizeds_client->async_send_request(
            std::make_shared<task_generator_msgs::srv::QueryParametrizeds::Request>(),
            [cb = std::move(callback)](rclcpp::Client<task_generator_msgs::srv::QueryParametrizeds>::SharedFuture f)
            {
                auto resp = f.get();
                cb(resp ? resp->ids : std::vector<std::string>{});
            });
    }
    else if (catalog_name == "environments")
    {
        query_environments_client->async_send_request(
            std::make_shared<task_generator_msgs::srv::QueryEnvironments::Request>(),
            [cb = std::move(callback)](rclcpp::Client<task_generator_msgs::srv::QueryEnvironments>::SharedFuture f)
            {
                auto resp = f.get();
                cb(resp ? resp->ids : std::vector<std::string>{});
            });
    }
    else
    {
        RCLCPP_WARN(node->get_logger(), "Unknown catalog: %s", catalog_name.c_str());
        callback({});
    }
}

// ---------------------------------------------------------------------------

void TaskGeneratorPanel::mirrorSharedParam(const std::string &leaf, bool from_obstacles)
{
    auto lower = [](std::string s) {
        for (char &c : s) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        return s;
    };
    const auto obs = lower(obstacles_task_mode.toStdString());
    const auto rob = lower(robots_task_mode.toStdString());
    if (obs.empty() || obs != rob) return;

    const auto &src_map   = from_obstacles ? param_widgets_obstacles_ : param_widgets_robots_;
    const auto &src_types = from_obstacles ? param_types_obstacles_   : param_types_robots_;
    auto       &dst_map   = from_obstacles ? param_widgets_robots_    : param_widgets_obstacles_;

    auto src_it  = src_map.find(leaf);
    auto dst_it  = dst_map.find(leaf);
    auto type_it = src_types.find(leaf);
    if (src_it == src_map.end() || dst_it == dst_map.end() || type_it == src_types.end())
        return;

    std::unordered_map<std::string, QWidget *> src_one  = {{leaf, src_it->second}};
    std::unordered_map<std::string, uint8_t>   type_one = {{leaf, type_it->second}};
    auto params = DynamicParamTree::collectParams(src_one, type_one);
    if (params.empty()) return;
    DynamicParamTree::setWidgetValueFromParam(dst_it->second, params.front());
}

} // namespace task_generator_gui
