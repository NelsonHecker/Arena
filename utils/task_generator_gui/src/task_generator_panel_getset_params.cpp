#include "task_generator_gui/task_generator_panel.hpp"
#include "rviz_common/display_context.hpp"

#include "rcl_interfaces/srv/set_parameters.hpp"

#include <chrono>
#include <cstdlib>
#include <memory>
#include <cctype>

namespace task_generator_gui
{
    void TaskGeneratorPanel::getRobots()
    {
        query_robots_client->async_send_request(
            std::make_shared<task_generator_msgs::srv::QueryRobots::Request>(),
            [this](rclcpp::Client<task_generator_msgs::srv::QueryRobots>::SharedFuture f)
            {
                auto resp = f.get();
                if (!resp) return;
                QMetaObject::invokeMethod(this, [this, ids = resp->ids]()
                {
                    robot_models = ids;
                    if (selected_robot_model.empty() && !robot_models.empty())
                        selected_robot_model = robot_models[0];
                    if (robot_combobox)
                    {
                        QSignalBlocker blocker(robot_combobox);
                        robot_combobox->clear();
                        for (const auto &r : robot_models)
                            robot_combobox->addItem(QString::fromStdString(r));
                        robot_combobox->setCurrentText(QString::fromStdString(selected_robot_model));
                    }
                }, Qt::QueuedConnection);
            });
    }

    void TaskGeneratorPanel::getWorlds()
    {
        query_worlds_client->async_send_request(
            std::make_shared<task_generator_msgs::srv::QueryWorlds::Request>(),
            [this](rclcpp::Client<task_generator_msgs::srv::QueryWorlds>::SharedFuture f)
            {
                auto resp = f.get();
                if (!resp) return;
                QMetaObject::invokeMethod(this, [this, ids = resp->ids]()
                {
                    worlds = ids;
                    if (staged_world.empty() && !worlds.empty())
                        staged_world = worlds[0];
                    if (world_combobox)
                    {
                        QSignalBlocker blocker(world_combobox);
                        world_combobox->clear();
                        for (const auto &w : worlds)
                            world_combobox->addItem(QString::fromStdString(w));
                        world_combobox->setCurrentText(QString::fromStdString(staged_world));
                    }
                }, Qt::QueuedConnection);
            });
    }

    void TaskGeneratorPanel::getTMObstaclesParams()
    {
        getScenarios(staged_world);
    }

    void TaskGeneratorPanel::getScenarios(const std::string &world_name)
    {
        (void)world_name;
        // Scenarios are fetched lazily via fetchCatalog("scenarios") in DynamicParamTree::rebuild.
    }

    void TaskGeneratorPanel::setTMObstaclesParamsRequest(task_generator_msgs::srv::QueueEpisode::Request &req)
    {
        auto tm_value = obstacles_task_mode.toStdString();
        for (char &c : tm_value)
            c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));

        req.tm_obstacles     = tm_value;
        req.obstacles_params = DynamicParamTree::collectParams(param_widgets_obstacles_, param_types_obstacles_);
    }

    void TaskGeneratorPanel::setTMRobotsParamsRequest(task_generator_msgs::srv::QueueEpisode::Request &req)
    {
        auto tm_value = robots_task_mode.toStdString();
        for (char &c : tm_value)
            c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));

        req.tm_robots     = tm_value;
        req.robots_params = DynamicParamTree::collectParams(param_widgets_robots_, param_types_robots_);
    }

    void TaskGeneratorPanel::getParams()
    {
        getRobots();
        getWorlds();
        updateTabs();
        getTMObstaclesParams();
    }

    task_generator_msgs::srv::QueueEpisode::Request::SharedPtr
    TaskGeneratorPanel::buildQueueEpisodeRequest()
    {
        auto req = std::make_shared<task_generator_msgs::srv::QueueEpisode::Request>();
        req->action       = task_generator_msgs::srv::QueueEpisode::Request::MERGE;
        req->keep_modules = true;
        req->world        = staged_world;

        setTMObstaclesParamsRequest(*req);
        setTMRobotsParamsRequest(*req);

        return req;
    }

    void TaskGeneratorPanel::pushQueueEpisode(std::function<void(bool)> on_done)
    {
        auto req = buildQueueEpisodeRequest();
        queue_episode_client->async_send_request(
            req,
            [this, on_done = std::move(on_done)]
            (rclcpp::Client<task_generator_msgs::srv::QueueEpisode>::SharedFuture f)
            {
                auto resp = f.get();
                const bool ok = resp && resp->success;
                if (resp && !ok)
                    RCLCPP_WARN(node->get_logger(),
                                "queue_episode rejected: %s", resp->error_msg.c_str());
                on_done(ok);
            });
    }

    void TaskGeneratorPanel::setRobot()
    {
        if (selected_robot_model.empty())
            return;

        auto req = std::make_shared<task_generator_msgs::srv::QueueEpisode::Request>();
        req->action       = task_generator_msgs::srv::QueueEpisode::Request::MERGE;
        req->keep_modules = true;
        req->robots       = {selected_robot_model};

        queue_episode_client->async_send_request(
            req,
            [this](rclcpp::Client<task_generator_msgs::srv::QueueEpisode>::SharedFuture f)
            {
                auto resp = f.get();
                if (resp && !resp->success)
                    RCLCPP_WARN(node->get_logger(),
                                "queue_episode rejected (spawn robot): %s",
                                resp->error_msg.c_str());
            });
    }

    std::vector<std::string> TaskGeneratorPanel::convert(const QStringList &qList)
    {
        std::vector<std::string> result;
        result.reserve(qList.size());
        for (const QString &item : qList)
            result.push_back(item.toStdString());
        return result;
    }

} // namespace task_generator_gui
