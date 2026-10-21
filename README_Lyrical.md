# ROS 2 Lyrical compatibility changes

> **Note:**
> - if *Cartographer* is not present in your `/opt/ros/${ROS_DISTRO}/share/cartographer_ros` you can build it as described below.
> - ROS2 *Lyrical* seems to distribute `/opt/ros/${ROS_DISTRO}/share/cartographer_ros_msgs` as binaries, but not the rest.
> - put COLCON_IGNORE file in directories which you don't want to be built.
> - see https://github.com/slgrobotics/articubot_one/wiki/Jazzy-to-Lyrical-migration for more.


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
## Headless Raspberry Pi 5 build notes

Cartographer and `cartographer_ros` were built successfully on a Raspberry Pi 5 running Ubuntu Server 26.04.1 and ROS 2 Lyrical (ROS Base).

### Package selection

Keep both the `cartographer` core repository and this `cartographer_ros` repository under the workspace's `src` directory. On the headless robot, build only the core library and ROS integration:

- Skip `cartographer_rviz`: RViz runs on a separate computer, so its plugin is unnecessary on the robot.
- Skip `cartographer_ros_msgs`: use the matching binary package already installed under `/opt/ros/lyrical`.

From the workspace's `src` directory:

```bash
cd ~/robot_ws/src
cp cartographer_ros/docs/COLCON_IGNORE cartographer_ros/cartographer_ros_msgs/
cp cartographer_ros/docs/COLCON_IGNORE cartographer_ros/cartographer_rviz/
```

These marker files tell colcon to ignore the two packages.

Build from the workspace root:

```bash
cd ~/robot_ws
source /opt/ros/lyrical/setup.bash
colcon build --packages-up-to cartographer_ros
source install/setup.bash
```

There is no need for `--allow-overriding cartographer_ros_msgs` when the source messages package is ignored.

### Compiler output

The successful Raspberry Pi builds produced substantial stderr output:

- **GCC ARM ABI notes:** Eigen rotation types trigger messages about parameter passing changing in GCC 10.1 when C++17 is enabled. These are informational notes, not compilation errors.
- **Deprecation warnings:** TF2's legacy `.h` headers, Abseil mutex locks constructed with pointers, and some offline-node APIs still compile under Lyrical but have newer replacements.

Colcon prints stderr even when a package succeeds. The supplied logs ended with `Finished <<< cartographer` and `Finished <<< cartographer_ros`; neither showed compilation errors. This confirms compilation, not full robot runtime validation.

To optionally suppress GCC's ABI notes on the Pi:

```bash
colcon build --packages-up-to cartographer_ros --cmake-args -DCMAKE_CXX_FLAGS=-Wno-psabi
```

This sets `CMAKE_CXX_FLAGS`; preserve any other custom flags if you already use them. It does not suppress the separate deprecation warnings.
