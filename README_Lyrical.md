# ROS 2 Lyrical compatibility changes

> **Note:**
> - if *Cartographer* is not present in your `/opt/ros/${ROS_DISTRO}/share/cartographer_ros` you can build it as described below.
> - ROS2 *Lyrical* seems to distribute `/opt/ros/${ROS_DISTRO}/share/cartographer_ros_msgs` as binaries, but not the rest.

## Cartographer (core library)

- Replaced legacy thread annotations (`GUARDED_BY`, `LOCKS_EXCLUDED`, and related macros) with their `ABSL_*` equivalents and explicitly included `absl/base/thread_annotations.h` for compatibility with the installed Abseil version.
- Raised the minimum CMake version to **3.16**.
- Switched Boost discovery to `find_package(Boost CONFIG ...)` in both the build and exported package configuration to support modern Boost/CMake packages.

## cartographer_ros (including messages and RViz)

- Applied the same Abseil annotation updates to the ROS integration and RViz plugin.
- Raised the minimum CMake version to **3.16** in the ROS, messages, RViz, and documentation packages.
- Moved `offline_node.cpp` from the shared ROS library into `cartographer_offline_node`, preventing duplicate gflags registrations (such as `collect_metrics`) when starting the live node. Added explicit URDF linkage to the offline executable and retained the header compatibility definition for older ROS distributions.

## Build and launch notes

Both repositories must be present under the workspace's `src` directory. Build and source the overlay:

```bash
mkdir -p ~/robot_ws/src
cd ~/robot_ws/src
git clone https://github.com/slgrobotics/cartographer.git -b lyrical
git clone https://github.com/slgrobotics/cartographer_ros.git -b lyrical

# At this point you may want to suppress building some of the packages:
# cp cartographer_ros/docs/COLCON_IGNORE cartographer_ros/cartographer_ros_msgs/.  # because binary package is present
# cp cartographer_ros/docs/COLCON_IGNORE cartographer_ros/cartographer_rviz/.      # on a "headless" robot with ROS2 Base

cd ~/robot_ws
colcon build --allow-overriding cartographer_ros_msgs
source install/setup.bash
```

**Note:** put COLCON_IGNORE file in directories which you don't want to be built.

