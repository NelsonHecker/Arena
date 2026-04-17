#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <tf2_ros/transform_broadcaster.h>
#include <geometry_msgs/msg/transform_stamped.hpp>

class PoseToTF : public rclcpp::Node
{
public:
  PoseToTF()
  : Node("pose_to_tf")
  {
    this->declare_parameter<std::string>("parent_frame", "odom");
    this->declare_parameter<std::string>("child_frame", "base_link");
    this->declare_parameter<std::string>("pose_topic", "pose");

    parent_frame_ = this->get_parameter("parent_frame").as_string();
    child_frame_ = this->get_parameter("child_frame").as_string();
    std::string pose_topic = this->get_parameter("pose_topic").as_string();

    subscription_ = this->create_subscription<geometry_msgs::msg::PoseStamped>(
      pose_topic, 10, std::bind(&PoseToTF::topic_callback, this, std::placeholders::_1));
    tf_broadcaster_ = std::make_unique<tf2_ros::TransformBroadcaster>(this);
  }

private:
  void topic_callback(const geometry_msgs::msg::PoseStamped::SharedPtr msg)
  {
    geometry_msgs::msg::TransformStamped transform_stamped;

    transform_stamped.header.stamp = msg->header.stamp;
    transform_stamped.header.frame_id = parent_frame_;
    transform_stamped.child_frame_id = child_frame_;

    transform_stamped.transform.translation.x = msg->pose.position.x;
    transform_stamped.transform.translation.y = msg->pose.position.y;
    transform_stamped.transform.translation.z = msg->pose.position.z;
    transform_stamped.transform.rotation = msg->pose.orientation;

    tf_broadcaster_->sendTransform(transform_stamped);
  }

  rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr subscription_;
  std::unique_ptr<tf2_ros::TransformBroadcaster> tf_broadcaster_;
  std::string parent_frame_;
  std::string child_frame_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<PoseToTF>());
  rclcpp::shutdown();
  return 0;
}
