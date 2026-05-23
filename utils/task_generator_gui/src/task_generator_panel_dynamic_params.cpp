#include "task_generator_gui/task_generator_panel.hpp"

#include <rcl_interfaces/msg/parameter_type.hpp>

#include <QWidget>
#include <QHBoxLayout>
#include <QLabel>
#include <QSpinBox>
#include <QDoubleSpinBox>
#include <QComboBox>
#include <QCheckBox>
#include <QLineEdit>
#include <QTextEdit>

#include <algorithm>
#include <cctype>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace task_generator_gui
{

namespace
{
using PT = rcl_interfaces::msg::ParameterType;

QWidget *make_int_pair_widget(int64_t v0, int64_t v1)
{
    auto *w   = new QWidget();
    auto *lay = new QHBoxLayout(w);
    lay->setContentsMargins(0, 0, 0, 0);
    lay->setSpacing(4);
    lay->addWidget(new QLabel("Min"));
    auto *sb0 = new QSpinBox();
    sb0->setRange(0, std::numeric_limits<int>::max());
    sb0->setValue(static_cast<int>(v0));
    lay->addWidget(sb0, 1);
    lay->addWidget(new QLabel("Max"));
    auto *sb1 = new QSpinBox();
    sb1->setRange(0, std::numeric_limits<int>::max());
    sb1->setValue(static_cast<int>(v1));
    lay->addWidget(sb1, 1);
    w->setLayout(lay);
    return w;
}

QWidget *make_float_pair_widget(double v0, double v1)
{
    auto *w   = new QWidget();
    auto *lay = new QHBoxLayout(w);
    lay->setContentsMargins(0, 0, 0, 0);
    lay->setSpacing(4);
    lay->addWidget(new QLabel("Min"));
    auto *sb0 = new QDoubleSpinBox();
    sb0->setRange(-1e9, 1e9);
    sb0->setValue(v0);
    lay->addWidget(sb0, 1);
    lay->addWidget(new QLabel("Max"));
    auto *sb1 = new QDoubleSpinBox();
    sb1->setRange(-1e9, 1e9);
    sb1->setValue(v1);
    lay->addWidget(sb1, 1);
    w->setLayout(lay);
    return w;
}
} // namespace

// ---------------------------------------------------------------------------

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
// Widget builder — called on Qt thread once all data has arrived.

void TaskGeneratorPanel::buildTreeWidgets(
    QTreeWidget *tree,
    std::unordered_map<std::string, QWidget *> &widget_map,
    const std::shared_ptr<RebuildState> &state)
{
    tree->clear();
    widget_map.clear();

    auto &type_map = state->is_obstacles ? param_types_obstacles_ : param_types_robots_;
    type_map.clear();

    const bool is_obstacles = state->is_obstacles;
    const std::string prefix = "task." + state->mode + ".";

    for (size_t i = 0; i < state->param_names.size(); ++i)
    {
        const auto &full_name = state->param_names[i];
        std::string leaf      = full_name;
        if (full_name.rfind(prefix, 0) == 0)
            leaf = full_name.substr(prefix.size());

        const auto &desc   = state->descriptors[i];
        const auto &param  = state->values[i];
        const uint8_t ptype = desc.type;

        std::string label;
        std::string constraints;
        {
            std::string rest = desc.additional_constraints;
            while (!rest.empty())
            {
                size_t semi  = rest.find(';');
                std::string token = (semi == std::string::npos) ? rest : rest.substr(0, semi);
                rest = (semi == std::string::npos) ? std::string() : rest.substr(semi + 1);
                size_t colon = token.find(':');
                if (colon == std::string::npos) continue;
                std::string kind  = token.substr(0, colon);
                std::string value = token.substr(colon + 1);
                if (kind == "label")
                    label = value;
                else
                    constraints = token;
            }
        }

        auto *item = new QTreeWidgetItem(tree);
        item->setText(0, QString::fromStdString(label.empty() ? leaf : label));
        if (!desc.description.empty())
            item->setToolTip(0, QString::fromStdString(desc.description));

        QWidget *w = nullptr;

        if (constraints == "range:int_pair" && ptype == PT::PARAMETER_INTEGER_ARRAY)
        {
            const auto &arr = param.as_integer_array();
            int64_t v0 = arr.size() > 0 ? arr[0] : 0;
            int64_t v1 = arr.size() > 1 ? arr[1] : 0;
            w = make_int_pair_widget(v0, v1);
        }
        else if (constraints == "range:float_pair" && ptype == PT::PARAMETER_DOUBLE_ARRAY)
        {
            const auto &arr = param.as_double_array();
            double v0 = arr.size() > 0 ? arr[0] : 0.0;
            double v1 = arr.size() > 1 ? arr[1] : 0.0;
            w = make_float_pair_widget(v0, v1);
        }
        else if (constraints.rfind("catalog:", 0) == 0 && ptype == PT::PARAMETER_STRING_ARRAY)
        {
            const std::string catalog_name = constraints.substr(8);
            const auto &items = state->catalog_cache[catalog_name];
            auto *cb = new MultiSelectComboBox();
            const auto &selected = param.as_string_array();
            for (const auto &entry : items)
            {
                int checked = std::find(selected.begin(), selected.end(), entry) != selected.end() ? 1 : 0;
                cb->addItem(QString::fromStdString(entry), checked);
            }
            cb->stateChanged(1);
            w = cb;
        }
        else if (constraints.rfind("catalog:", 0) == 0 && ptype == PT::PARAMETER_STRING)
        {
            const std::string catalog_name = constraints.substr(8);
            const auto &items = state->catalog_cache[catalog_name];
            auto *cb = new QComboBox();
            for (const auto &entry : items)
                cb->addItem(QString::fromStdString(entry));
            cb->setCurrentText(QString::fromStdString(param.as_string()));
            w = cb;
        }
        else if (constraints.rfind("enum:", 0) == 0 && ptype == PT::PARAMETER_STRING)
        {
            auto *cb   = new QComboBox();
            std::string rest = constraints.substr(5);
            size_t start = 0;
            while (start <= rest.size())
            {
                size_t comma = rest.find(',', start);
                std::string tok = rest.substr(start, comma == std::string::npos ? std::string::npos : comma - start);
                if (!tok.empty()) cb->addItem(QString::fromStdString(tok));
                if (comma == std::string::npos) break;
                start = comma + 1;
            }
            cb->setCurrentText(QString::fromStdString(param.as_string()));
            w = cb;
        }
        else if (ptype == PT::PARAMETER_INTEGER && !desc.integer_range.empty())
        {
            auto *sb = new QSpinBox();
            sb->setRange(
                static_cast<int>(desc.integer_range[0].from_value),
                static_cast<int>(desc.integer_range[0].to_value));
            sb->setValue(static_cast<int>(param.as_int()));
            w = sb;
        }
        else if (ptype == PT::PARAMETER_DOUBLE && !desc.floating_point_range.empty())
        {
            auto *sb = new QDoubleSpinBox();
            sb->setRange(desc.floating_point_range[0].from_value,
                         desc.floating_point_range[0].to_value);
            if (desc.floating_point_range[0].step > 0.0)
                sb->setSingleStep(desc.floating_point_range[0].step);
            sb->setValue(param.as_double());
            w = sb;
        }
        else if (ptype == PT::PARAMETER_BOOL)
        {
            auto *cb = new QCheckBox();
            cb->setChecked(param.as_bool());
            w = cb;
        }
        else if (ptype == PT::PARAMETER_INTEGER)
        {
            auto *sb = new QSpinBox();
            sb->setRange(std::numeric_limits<int>::min(), std::numeric_limits<int>::max());
            sb->setValue(static_cast<int>(param.as_int()));
            w = sb;
        }
        else if (ptype == PT::PARAMETER_DOUBLE)
        {
            auto *sb = new QDoubleSpinBox();
            sb->setRange(-1e9, 1e9);
            sb->setValue(param.as_double());
            w = sb;
        }
        else if (ptype == PT::PARAMETER_STRING)
        {
            const auto val = param.as_string();
            if (val.size() > 80 || desc.description.find("prompt") != std::string::npos
                || leaf.find("prompt") != std::string::npos)
            {
                auto *te = new QTextEdit();
                te->setPlainText(QString::fromStdString(val));
                te->setMinimumHeight(50);
                te->setWordWrapMode(QTextOption::WrapAtWordBoundaryOrAnywhere);
                te->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Minimum);
                te->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
                te->setLineWrapMode(QTextEdit::WidgetWidth);
                w = te;
            }
            else
            {
                auto *le = new QLineEdit();
                le->setText(QString::fromStdString(val));
                w = le;
            }
        }
        else
        {
            auto *le = new QLineEdit();
            le->setText(QString::fromStdString(param.value_to_string()));
            w = le;
        }

        if (w)
        {
            // Connect value-changed signals to bump the appropriate dirty flag,
            // and mirror the value to the twin tree when modes share namespace.
            if (auto *sb = qobject_cast<QSpinBox *>(w))
            {
                connect(sb, QOverload<int>::of(&QSpinBox::valueChanged), this,
                    [this, is_obstacles, leaf]()
                    {
                        if (loading_from_queue_) return;
                        if (is_obstacles) obstacles_params_dirty_ = true;
                        else              robots_params_dirty_    = true;
                        mirrorSharedParam(leaf, is_obstacles);
                        updateDirtyButtons();
                    });
            }
            else if (auto *dsb = qobject_cast<QDoubleSpinBox *>(w))
            {
                connect(dsb, QOverload<double>::of(&QDoubleSpinBox::valueChanged), this,
                    [this, is_obstacles, leaf]()
                    {
                        if (loading_from_queue_) return;
                        if (is_obstacles) obstacles_params_dirty_ = true;
                        else              robots_params_dirty_    = true;
                        mirrorSharedParam(leaf, is_obstacles);
                        updateDirtyButtons();
                    });
            }
            else if (auto *le = qobject_cast<QLineEdit *>(w))
            {
                connect(le, &QLineEdit::editingFinished, this,
                    [this, is_obstacles, leaf]()
                    {
                        if (loading_from_queue_) return;
                        if (is_obstacles) obstacles_params_dirty_ = true;
                        else              robots_params_dirty_    = true;
                        mirrorSharedParam(leaf, is_obstacles);
                        updateDirtyButtons();
                    });
            }
            else if (auto *cb = qobject_cast<QCheckBox *>(w))
            {
                connect(cb, &QCheckBox::toggled, this,
                    [this, is_obstacles, leaf](bool)
                    {
                        if (loading_from_queue_) return;
                        if (is_obstacles) obstacles_params_dirty_ = true;
                        else              robots_params_dirty_    = true;
                        mirrorSharedParam(leaf, is_obstacles);
                        updateDirtyButtons();
                    });
            }
            else if (auto *combo = qobject_cast<QComboBox *>(w))
            {
                connect(combo, &QComboBox::currentTextChanged, this,
                    [this, is_obstacles, leaf](const QString &)
                    {
                        if (loading_from_queue_) return;
                        if (is_obstacles) obstacles_params_dirty_ = true;
                        else              robots_params_dirty_    = true;
                        mirrorSharedParam(leaf, is_obstacles);
                        updateDirtyButtons();
                    });
            }
            else
            {
                // Composite pair widgets: connect children individually.
                for (auto *child_sb : w->findChildren<QSpinBox *>())
                {
                    connect(child_sb, QOverload<int>::of(&QSpinBox::valueChanged), this,
                        [this, is_obstacles, leaf]()
                        {
                            if (loading_from_queue_) return;
                            if (is_obstacles) obstacles_params_dirty_ = true;
                            else              robots_params_dirty_    = true;
                            mirrorSharedParam(leaf, is_obstacles);
                            updateDirtyButtons();
                        });
                }
                for (auto *child_dsb : w->findChildren<QDoubleSpinBox *>())
                {
                    connect(child_dsb, QOverload<double>::of(&QDoubleSpinBox::valueChanged), this,
                        [this, is_obstacles, leaf]()
                        {
                            if (loading_from_queue_) return;
                            if (is_obstacles) obstacles_params_dirty_ = true;
                            else              robots_params_dirty_    = true;
                            mirrorSharedParam(leaf, is_obstacles);
                            updateDirtyButtons();
                        });
                }
            }

            tree->setItemWidget(item, 1, w);
            widget_map[leaf] = w;
            type_map[leaf]   = ptype;
        }
    }
}

// ---------------------------------------------------------------------------

void TaskGeneratorPanel::rebuildParamTree(
    QTreeWidget *tree,
    const std::string &mode,
    std::unordered_map<std::string, QWidget *> &widget_map)
{
    if (!parameters_client || !tree)
        return;

    const bool is_obstacles = (&widget_map == &param_widgets_obstacles_);

    // Increment generation for this family; lambdas bail if stale.
    uint64_t &gen_counter = is_obstacles ? rebuild_gen_obstacles_ : rebuild_gen_robots_;
    const uint64_t this_gen = ++gen_counter;

    auto state         = std::make_shared<RebuildState>();
    state->generation  = this_gen;
    state->mode        = mode;
    state->is_obstacles = is_obstacles;

    const std::string list_prefix = "task." + mode;

    // Step 1: list_parameters
    parameters_client->list_parameters(
        {list_prefix}, 10,
        [this, tree, &widget_map, state, this_gen, is_obstacles]
        (std::shared_future<rcl_interfaces::msg::ListParametersResult> list_f)
        {
            rcl_interfaces::msg::ListParametersResult list_resp;
            try { list_resp = list_f.get(); } catch (...) { return; }

            if (list_resp.names.empty()) return;

            state->param_names = list_resp.names;

            // Step 2a+2b: describe and get in parallel.
            // Use a shared counter so the last-to-arrive fires catalog fan-out.
            auto describe_done = std::make_shared<std::atomic<bool>>(false);
            auto get_done      = std::make_shared<std::atomic<bool>>(false);

            auto maybe_fanout = [this, tree, &widget_map, state, this_gen, is_obstacles,
                                 describe_done, get_done]()
            {
                if (!describe_done->load() || !get_done->load())
                    return;

                // Check generation still valid.
                const uint64_t &cur_gen = is_obstacles ? rebuild_gen_obstacles_ : rebuild_gen_robots_;
                if (this_gen != cur_gen) return;

                // Drop YAML-loaded but undeclared params, describe_parameters
                // returns PARAMETER_NOT_SET for those, so they have no real widget contract.
                if (state->descriptors.size() == state->param_names.size()
                    && state->values.size() == state->param_names.size())
                {
                    std::vector<std::string> kept_names;
                    std::vector<rcl_interfaces::msg::ParameterDescriptor> kept_descs;
                    std::vector<rclcpp::Parameter> kept_values;
                    kept_names.reserve(state->param_names.size());
                    kept_descs.reserve(state->descriptors.size());
                    kept_values.reserve(state->values.size());
                    for (size_t i = 0; i < state->param_names.size(); ++i)
                    {
                        if (state->descriptors[i].type == rcl_interfaces::msg::ParameterType::PARAMETER_NOT_SET)
                            continue;
                        kept_names.push_back(state->param_names[i]);
                        kept_descs.push_back(state->descriptors[i]);
                        kept_values.push_back(state->values[i]);
                    }
                    state->param_names = std::move(kept_names);
                    state->descriptors = std::move(kept_descs);
                    state->values      = std::move(kept_values);
                }

                // Collect needed catalogs from descriptors.
                std::set<std::string> needed;
                for (const auto &desc : state->descriptors)
                {
                    std::string rest = desc.additional_constraints;
                    while (!rest.empty())
                    {
                        size_t semi  = rest.find(';');
                        std::string token = (semi == std::string::npos) ? rest : rest.substr(0, semi);
                        rest = (semi == std::string::npos) ? std::string() : rest.substr(semi + 1);
                        if (token.rfind("catalog:", 0) == 0)
                            needed.insert(token.substr(8));
                    }
                }
                {
                    std::lock_guard<std::mutex> lk(state->mtx);
                    state->needed_catalogs = needed;
                }

                if (needed.empty())
                {
                    QMetaObject::invokeMethod(this, [this, tree, &widget_map, state, this_gen, is_obstacles]()
                    {
                        const uint64_t &cur = is_obstacles ? rebuild_gen_obstacles_ : rebuild_gen_robots_;
                        if (this_gen != cur) return;
                        buildTreeWidgets(tree, widget_map, state);
                    }, Qt::QueuedConnection);
                    return;
                }

                state->pending_catalogs.store(static_cast<int>(needed.size()));

                for (const auto &cat : needed)
                {
                    fetchCatalog(
                        cat,
                        [this, tree, &widget_map, state, this_gen, is_obstacles, cat]
                        (std::vector<std::string> ids)
                        {
                            {
                                std::lock_guard<std::mutex> lk(state->mtx);
                                state->catalog_cache[cat] = std::move(ids);
                            }
                            if (--state->pending_catalogs == 0)
                            {
                                QMetaObject::invokeMethod(this,
                                    [this, tree, &widget_map, state, this_gen, is_obstacles]()
                                    {
                                        const uint64_t &cur = is_obstacles ? rebuild_gen_obstacles_ : rebuild_gen_robots_;
                                        if (this_gen != cur) return;
                                        buildTreeWidgets(tree, widget_map, state);
                                    }, Qt::QueuedConnection);
                            }
                        });
                }
            };

            // describe_parameters
            parameters_client->describe_parameters(
                state->param_names,
                [state, describe_done, maybe_fanout]
                (std::shared_future<std::vector<rcl_interfaces::msg::ParameterDescriptor>> f)
                {
                    try { state->descriptors = f.get(); } catch (...) {}
                    describe_done->store(true);
                    maybe_fanout();
                });

            // get_parameters
            parameters_client->get_parameters(
                state->param_names,
                [state, get_done, maybe_fanout]
                (std::shared_future<std::vector<rclcpp::Parameter>> f)
                {
                    try { state->values = f.get(); } catch (...) {}
                    get_done->store(true);
                    maybe_fanout();
                });
        });
}

// ---------------------------------------------------------------------------

void TaskGeneratorPanel::setWidgetValueFromParam(QWidget *w, const rcl_interfaces::msg::Parameter &p)
{
    using PT = rcl_interfaces::msg::ParameterType;

    const uint8_t ptype = p.value.type;

    if (ptype == PT::PARAMETER_INTEGER)
    {
        if (auto *sb = qobject_cast<QSpinBox *>(w))
        {
            QSignalBlocker blk(sb);
            sb->setValue(static_cast<int>(p.value.integer_value));
        }
    }
    else if (ptype == PT::PARAMETER_DOUBLE)
    {
        if (auto *dsb = qobject_cast<QDoubleSpinBox *>(w))
        {
            QSignalBlocker blk(dsb);
            dsb->setValue(p.value.double_value);
        }
    }
    else if (ptype == PT::PARAMETER_BOOL)
    {
        if (auto *cb = qobject_cast<QCheckBox *>(w))
        {
            QSignalBlocker blk(cb);
            cb->setChecked(p.value.bool_value);
        }
    }
    else if (ptype == PT::PARAMETER_STRING)
    {
        if (auto *combo = qobject_cast<QComboBox *>(w))
        {
            QSignalBlocker blk(combo);
            combo->setCurrentText(QString::fromStdString(p.value.string_value));
        }
        else if (auto *te = qobject_cast<QTextEdit *>(w))
        {
            QSignalBlocker blk(te);
            te->setPlainText(QString::fromStdString(p.value.string_value));
        }
        else if (auto *le = qobject_cast<QLineEdit *>(w))
        {
            QSignalBlocker blk(le);
            le->setText(QString::fromStdString(p.value.string_value));
        }
    }
    else if (ptype == PT::PARAMETER_INTEGER_ARRAY)
    {
        auto children = w->findChildren<QSpinBox *>();
        const auto &arr = p.value.integer_array_value;
        for (size_t idx = 0; idx < static_cast<size_t>(children.size()) && idx < arr.size(); ++idx)
        {
            QSignalBlocker blk(children[static_cast<int>(idx)]);
            children[static_cast<int>(idx)]->setValue(static_cast<int>(arr[idx]));
        }
    }
    else if (ptype == PT::PARAMETER_DOUBLE_ARRAY)
    {
        auto children = w->findChildren<QDoubleSpinBox *>();
        const auto &arr = p.value.double_array_value;
        for (size_t idx = 0; idx < static_cast<size_t>(children.size()) && idx < arr.size(); ++idx)
        {
            QSignalBlocker blk(children[static_cast<int>(idx)]);
            children[static_cast<int>(idx)]->setValue(arr[idx]);
        }
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
    auto params = collectParamsFor(src_one, type_one);
    if (params.empty()) return;
    setWidgetValueFromParam(dst_it->second, params.front());
}

// ---------------------------------------------------------------------------

std::vector<rcl_interfaces::msg::Parameter> TaskGeneratorPanel::collectParamsFor(
    const std::unordered_map<std::string, QWidget *> &widget_map,
    const std::unordered_map<std::string, uint8_t> &type_map)
{
    std::vector<rcl_interfaces::msg::Parameter> result;

    for (const auto &[leaf, w] : widget_map)
    {
        auto it = type_map.find(leaf);
        if (it == type_map.end())
            continue;
        const uint8_t ptype = it->second;

        rcl_interfaces::msg::Parameter p;
        p.name = leaf;

        if (ptype == PT::PARAMETER_INTEGER_ARRAY)
        {
            auto children = w->findChildren<QSpinBox *>();
            if (children.size() >= 2)
            {
                p.value.type = PT::PARAMETER_INTEGER_ARRAY;
                p.value.integer_array_value = {
                    static_cast<int64_t>(children[0]->value()),
                    static_cast<int64_t>(children[1]->value())};
            }
            else
                continue;
        }
        else if (ptype == PT::PARAMETER_DOUBLE_ARRAY)
        {
            auto children = w->findChildren<QDoubleSpinBox *>();
            if (children.size() >= 2)
            {
                p.value.type = PT::PARAMETER_DOUBLE_ARRAY;
                p.value.double_array_value = {children[0]->value(), children[1]->value()};
            }
            else
                continue;
        }
        else if (ptype == PT::PARAMETER_STRING_ARRAY)
        {
            auto *cb = qobject_cast<MultiSelectComboBox *>(w);
            if (!cb) continue;
            p.value.type = PT::PARAMETER_STRING_ARRAY;
            for (const QString &s : cb->currentText())
                p.value.string_array_value.push_back(s.toStdString());
        }
        else if (ptype == PT::PARAMETER_STRING)
        {
            p.value.type = PT::PARAMETER_STRING;
            if (auto *cb = qobject_cast<QComboBox *>(w))
                p.value.string_value = cb->currentText().toStdString();
            else if (auto *te = qobject_cast<QTextEdit *>(w))
                p.value.string_value = te->toPlainText().toStdString();
            else if (auto *le = qobject_cast<QLineEdit *>(w))
                p.value.string_value = le->text().toStdString();
            else
                continue;
        }
        else if (ptype == PT::PARAMETER_BOOL)
        {
            auto *cb = qobject_cast<QCheckBox *>(w);
            if (!cb) continue;
            p.value.type = PT::PARAMETER_BOOL;
            p.value.bool_value = cb->isChecked();
        }
        else if (ptype == PT::PARAMETER_INTEGER)
        {
            auto *sb = qobject_cast<QSpinBox *>(w);
            if (!sb) continue;
            p.value.type = PT::PARAMETER_INTEGER;
            p.value.integer_value = sb->value();
        }
        else if (ptype == PT::PARAMETER_DOUBLE)
        {
            auto *sb = qobject_cast<QDoubleSpinBox *>(w);
            if (!sb) continue;
            p.value.type = PT::PARAMETER_DOUBLE;
            p.value.double_value = sb->value();
        }
        else
        {
            if (auto *le = qobject_cast<QLineEdit *>(w))
            {
                p.value.type = PT::PARAMETER_STRING;
                p.value.string_value = le->text().toStdString();
            }
            else
                continue;
        }

        result.push_back(std::move(p));
    }

    return result;
}

} // namespace task_generator_gui
