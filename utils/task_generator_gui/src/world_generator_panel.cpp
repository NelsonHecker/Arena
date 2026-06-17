#include "task_generator_gui/world_generator_panel.hpp"
#include "rviz_common/display_context.hpp"

#include <rcl_interfaces/msg/parameter.hpp>
#include <rclcpp/parameter.hpp>
#include <rclcpp/parameter_value.hpp>

#include <QByteArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QMetaObject>

#include <chrono>
#include <climits>
#include <set>
#include <string>
#include <vector>

namespace task_generator_gui
{

WorldGeneratorPanel::WorldGeneratorPanel(QWidget* parent)
: Panel(parent)
{
}

WorldGeneratorPanel::~WorldGeneratorPanel() = default;

void WorldGeneratorPanel::onInitialize()
{
    node_ptr = getDisplayContext()->getRosNodeAbstraction().lock();
    node = node_ptr->get_raw_node();
    node->get_logger().set_level(rclcpp::Logger::Level::Warn);
}

void WorldGeneratorPanel::load(const rviz_common::Config& config)
{
    rviz_common::Panel::load(config);

    QString result;
    if (config.mapGetString("WorldGeneratorTarget", &result))
        world_generator_node = result.toStdString();
    else
        world_generator_node = "/world_generator";

    if (config.mapGetString("Target", &result))
        task_generator_node = result.toStdString();
    else
        task_generator_node = "/task_generator_node";

    params_client_ = std::make_shared<rclcpp::AsyncParametersClient>(node, world_generator_node);

    generate_client_ = node->create_client<std_srvs::srv::Trigger>(
        world_generator_node + "/generate_world");

    queue_episode_client_ = node->create_client<task_generator_msgs::srv::QueueEpisode>(
        task_generator_node + "/config/queue_episode");

    reset_episode_client_ = node->create_client<task_generator_msgs::srv::ResetEpisode>(
        task_generator_node + "/lifecycle/reset_episode");

    setupUi();

    param_tree_engine_ = std::make_unique<DynamicParamTree>(
        node,
        params_client_,
        param_tree_,
        &param_widgets_,
        &param_types_,
        [](const std::string&) {},
        nullptr);

    connect(algorithm_combobox_, &QComboBox::currentTextChanged,
            this, &WorldGeneratorPanel::onAlgorithmChanged);

    loadAlgorithms();
}

void WorldGeneratorPanel::loadAlgorithms()
{
    // Poll until the world_generator param service is up and the algorithm list
    // is non-empty; under gazebo the node and its params come up well after rviz.
    auto holder    = std::make_shared<rclcpp::TimerBase::SharedPtr>();
    auto in_flight = std::make_shared<bool>(false);

    auto tick = [this, holder, in_flight]()
    {
        if (*in_flight || !params_client_->service_is_ready()) return;
        *in_flight = true;
        params_client_->list_parameters(
            {"algorithm"}, 10,
            [this, holder, in_flight](std::shared_future<rcl_interfaces::msg::ListParametersResult> future)
            {
                rcl_interfaces::msg::ListParametersResult resp;
                try { resp = future.get(); } catch (...) { *in_flight = false; return; }

                std::set<std::string> algos;
                for (const auto& name : resp.names)
                {
                    const std::string prefix = "algorithm.";
                    if (name.rfind(prefix, 0) != 0) continue;
                    auto rest = name.substr(prefix.size());
                    auto dot  = rest.find('.');
                    if (dot == std::string::npos) continue;
                    algos.insert(rest.substr(0, dot));
                }

                if (algos.empty()) { *in_flight = false; return; }  // params not declared yet; keep polling

                if (*holder) (*holder)->cancel();
                holder->reset();

                QMetaObject::invokeMethod(this, [this, algos]()
                {
                    {
                        QSignalBlocker blocker(algorithm_combobox_);
                        algorithm_combobox_->clear();
                        for (const auto& a : algos)
                            algorithm_combobox_->addItem(QString::fromStdString(a));
                    }
                    const auto& first = *algos.begin();
                    algorithm_combobox_->setCurrentText(QString::fromStdString(first));
                    param_tree_engine_->rebuild("algorithm." + first);
                }, Qt::QueuedConnection);
            });
    };

    *holder = node->create_wall_timer(std::chrono::milliseconds(500), std::move(tick));
}

void WorldGeneratorPanel::applyEpisodeBinding(
    task_generator_msgs::srv::QueueEpisode::Request& req, const std::string& json)
{
    // generate_world returns the generator's episode binding as JSON ({} = no overrides).
    auto doc = QJsonDocument::fromJson(QByteArray::fromStdString(json));
    if (!doc.isObject()) return;
    const QJsonObject obj = doc.object();

    if (obj.contains("tm_robots"))
        req.tm_robots = obj.value("tm_robots").toString().toStdString();
    if (obj.contains("tm_obstacles"))
        req.tm_obstacles = obj.value("tm_obstacles").toString().toStdString();

    // Binding param values are strings (the only kind generators emit); the target task params are string-typed.
    auto leaves = [](const QJsonValue& v) -> std::vector<rcl_interfaces::msg::Parameter>
    {
        std::vector<rcl_interfaces::msg::Parameter> out;
        if (!v.isObject()) return out;
        const QJsonObject leaf_obj = v.toObject();
        for (auto it = leaf_obj.begin(); it != leaf_obj.end(); ++it)
        {
            rcl_interfaces::msg::Parameter pm;
            pm.name  = it.key().toStdString();
            pm.value = rclcpp::ParameterValue(it.value().toString().toStdString()).to_value_msg();
            out.push_back(pm);
        }
        return out;
    };

    auto robots    = leaves(obj.value("robots_params"));
    auto obstacles = leaves(obj.value("obstacles_params"));
    req.robots_params.insert(req.robots_params.end(), robots.begin(), robots.end());
    req.obstacles_params.insert(req.obstacles_params.end(), obstacles.begin(), obstacles.end());
}

void WorldGeneratorPanel::setupUi()
{
    auto* root = new QVBoxLayout(this);

    // Algorithm row
    {
        auto* row    = new QWidget();
        auto* layout = new QHBoxLayout(row);
        layout->addWidget(new QLabel("Algorithm"));
        algorithm_combobox_ = new QComboBox();
        layout->addWidget(algorithm_combobox_);
        root->addWidget(row);
    }

    // World name row
    {
        auto* row    = new QWidget();
        auto* layout = new QHBoxLayout(row);
        layout->addWidget(new QLabel("World Name"));
        world_name_edit_ = new QLineEdit("generated");
        layout->addWidget(world_name_edit_);
        root->addWidget(row);
    }

    // Seed row
    {
        auto* row    = new QWidget();
        auto* layout = new QHBoxLayout(row);
        layout->addWidget(new QLabel("Seed (-1 = random)"));
        seed_spin_ = new QSpinBox();
        seed_spin_->setRange(-1, INT_MAX);
        seed_spin_->setValue(-1);
        layout->addWidget(seed_spin_);
        root->addWidget(row);
    }

    // Parameter tree
    param_tree_ = new QTreeWidget();
    param_tree_->setColumnCount(2);
    param_tree_->setHeaderLabels({"Parameter", "Value"});
    param_tree_->header()->setSectionResizeMode(QHeaderView::Stretch);
    root->addWidget(param_tree_);

    generate_button_ = new QPushButton("Generate");
    connect(generate_button_, &QPushButton::clicked,
            this, &WorldGeneratorPanel::onGenerateClicked);
    root->addWidget(generate_button_);

    status_label_ = new QLabel();
    status_label_->setWordWrap(true);
    root->addWidget(status_label_);
}

void WorldGeneratorPanel::onAlgorithmChanged(const QString& text)
{
    param_tree_engine_->rebuild("algorithm." + text.toStdString());
}

void WorldGeneratorPanel::onGenerateClicked()
{
    const std::string algo   = algorithm_combobox_->currentText().toStdString();
    const std::string target = world_name_edit_->text().toStdString();

    if (target.empty())
    {
        status_label_->setText("World name must not be empty.");
        return;
    }

    generate_button_->setEnabled(false);
    status_label_->setText("Setting parameters...");

    auto leaves = DynamicParamTree::collectParams(param_widgets_, param_types_);

    std::vector<rclcpp::Parameter> params;
    params.reserve(leaves.size() + 3);

    for (auto& leaf : leaves)
    {
        auto copy  = leaf;
        copy.name  = "algorithm." + algo + "." + leaf.name;
        params.push_back(rclcpp::Parameter::from_parameter_msg(copy));
    }
    params.emplace_back("generator", algo);
    params.emplace_back("world",     target);
    params.emplace_back("seed",      static_cast<int64_t>(seed_spin_->value()));

    params_client_->set_parameters(
        params,
        [this, target](
            std::shared_future<std::vector<rcl_interfaces::msg::SetParametersResult>> future)
        {
            auto results = future.get();
            for (const auto& r : results)
            {
                if (!r.successful)
                {
                    const std::string msg = "Set parameter failed: " + r.reason;
                    QMetaObject::invokeMethod(this, [this, msg]()
                    {
                        status_label_->setText(QString::fromStdString(msg));
                        generate_button_->setEnabled(true);
                    }, Qt::QueuedConnection);
                    return;
                }
            }

            QMetaObject::invokeMethod(this, [this]()
            {
                status_label_->setText("Generating...");
            }, Qt::QueuedConnection);

            auto req = std::make_shared<std_srvs::srv::Trigger::Request>();
            generate_client_->async_send_request(
                req,
                [this, target](rclcpp::Client<std_srvs::srv::Trigger>::SharedFuture f)
                {
                    auto resp = f.get();
                    if (!resp || !resp->success)
                    {
                        const std::string msg = resp ? resp->message : "No response from generate_world.";
                        QMetaObject::invokeMethod(this, [this, msg]()
                        {
                            status_label_->setText(QString::fromStdString(msg));
                            generate_button_->setEnabled(true);
                        }, Qt::QueuedConnection);
                        return;
                    }

                    const std::string ok_msg = "World '" + target + "' generated!";
                    QMetaObject::invokeMethod(this, [this, ok_msg]()
                    {
                        status_label_->setText(QString::fromStdString(ok_msg));
                    }, Qt::QueuedConnection);

                    auto qreq = std::make_shared<task_generator_msgs::srv::QueueEpisode::Request>();
                    qreq->action       = task_generator_msgs::srv::QueueEpisode::Request::MERGE;
                    qreq->keep_modules = true;
                    qreq->world        = target;

                    // The generator returns its episode binding (e.g. BARN pins robots to scenario mode).
                    applyEpisodeBinding(*qreq, resp->message);

                    queue_episode_client_->async_send_request(
                        qreq,
                        [this, target](rclcpp::Client<task_generator_msgs::srv::QueueEpisode>::SharedFuture qf)
                        {
                            auto qresp = qf.get();
                            if (!qresp || !qresp->success)
                            {
                                RCLCPP_WARN(node->get_logger(), "staging generated world into task generator failed");
                                QMetaObject::invokeMethod(this, [this]() { generate_button_->setEnabled(true); }, Qt::QueuedConnection);
                                return;
                            }

                            // Apply the staged world now by resetting the episode.
                            auto rreq = std::make_shared<task_generator_msgs::srv::ResetEpisode::Request>();
                            rreq->world = target;
                            reset_episode_client_->async_send_request(
                                rreq,
                                [this](rclcpp::Client<task_generator_msgs::srv::ResetEpisode>::SharedFuture rf)
                                {
                                    auto rresp = rf.get();
                                    if (!rresp || !rresp->success)
                                        RCLCPP_WARN(node->get_logger(), "applying generated world (reset_episode) failed");

                                    QMetaObject::invokeMethod(this, [this]() { generate_button_->setEnabled(true); }, Qt::QueuedConnection);
                                });
                        });
                });
        });
}

} // namespace task_generator_gui

#include <pluginlib/class_list_macros.hpp>
PLUGINLIB_EXPORT_CLASS(task_generator_gui::WorldGeneratorPanel, rviz_common::Panel)
