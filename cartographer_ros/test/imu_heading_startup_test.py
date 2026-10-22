#!/usr/bin/env python3
"""Live integration checks; run after building and sourcing both repositories.

Uses an isolated ROS domain, synthetic stationary scans, and temporary logs.
No robot hardware is required.
"""
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

# Override before importing ROS libraries so no robot domain is contacted.
os.environ['ROS_DOMAIN_ID'] = '173'

import rclpy
from ament_index_python.packages import get_package_prefix
from cartographer_ros_msgs.msg import SubmapList
from geometry_msgs.msg import TransformStamped
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu, LaserScan
from tf2_ros import StaticTransformBroadcaster


class ImuHeadingStartupTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='cartographer-heading-')
        self.root = Path(self.directory.name)
        self.env = dict(os.environ, ROS_LOG_DIR=str(self.root / 'roslogs'))
        self.node = rclpy.create_node('heading_startup_test')
        self.imu = self.node.create_publisher(Imu, '/imu', qos_profile_sensor_data)
        self.scan = self.node.create_publisher(LaserScan, '/scan', qos_profile_sensor_data)
        self.submaps = []
        self.subscription = self.node.create_subscription(
            SubmapList, '/submap_list', self.submaps.append, 10)
        self.static_tf = StaticTransformBroadcaster(self.node)
        source = Path(__file__).resolve().parents[1] / 'configuration_files/revo_lds.lua'
        config = source.read_text().replace('horizontal_laser_link', 'base_link')
        config = config.replace('return options', '''
options.initialize_map_from_imu = true
options.imu_heading_offset_rad = 0.2
options.imu_heading_max_age_sec = 0.5
options.imu_heading_timeout_sec = 10.
return options''')
        self.config = self.root / 'heading.lua'
        self.config.write_text(config)
        self.process = None
        self.output = (self.root / 'node.log').open('w')

    def tearDown(self):
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.output.close()
        self.node.destroy_node()
        self.directory.cleanup()

    def start(self, extra=()):
        executable = Path(get_package_prefix('cartographer_ros')) / 'lib/cartographer_ros/cartographer_node'
        self.process = subprocess.Popen([
            str(executable), '-configuration_directory=' + str(self.root),
            '-configuration_basename=heading.lua',
            '-save_state_filename=' + str(self.root / 'state.pbstream'), *extra],
            env=self.env, stdout=self.output, stderr=subprocess.STDOUT)

    def log(self):
        return (self.root / 'node.log').read_text()

    def pump(self, seconds, yaw=None, invalid=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            stamp = self.node.get_clock().now().to_msg()
            scan = LaserScan()
            scan.header.stamp = stamp
            scan.header.frame_id = 'base_link'
            scan.angle_min = -1.
            scan.angle_max = 1.
            scan.angle_increment = .1
            scan.range_min = .3
            scan.range_max = 8.
            scan.ranges = [2.] * 21
            self.scan.publish(scan)
            if yaw is not None:
                msg = Imu()
                msg.header.stamp = stamp
                msg.header.frame_id = 'imu_link'
                msg.orientation.z = math.sin(yaw / 2)
                msg.orientation.w = math.cos(yaw / 2)
                msg.linear_acceleration.z = 9.81
                if invalid == 'unavailable':
                    msg.orientation_covariance[0] = -1.
                elif invalid == 'stale':
                    msg.header.stamp.sec -= 10
                elif invalid == 'quaternion':
                    msg.orientation.z = msg.orientation.w = 0.
                self.imu.publish(msg)
            rclpy.spin_once(self.node, timeout_sec=.03)

    def check_heading(self, imu_yaw):
        self.start()
        deadline = time.monotonic() + 5
        while 'Waiting for initial ENU' not in self.log() and time.monotonic() < deadline:
            self.pump(.1)
        self.assertIn('Waiting for initial ENU', self.log())
        for invalid in ('unavailable', 'stale', 'quaternion', None):
            # The valid orientation also must not start mapping without its TF.
            self.pump(.35, imu_yaw, invalid)
            self.assertFalse(any(msg.submap for msg in self.submaps), self.log())
            self.assertNotIn('starting the first trajectory', self.log())
            self.assertIsNone(self.process.poll(), self.log())
        transform = TransformStamped()
        transform.header.stamp = self.node.get_clock().now().to_msg()
        transform.header.frame_id = 'base_link'
        transform.child_frame_id = 'imu_link'
        transform.transform.rotation.z = math.sin(.3 / 2)
        transform.transform.rotation.w = math.cos(.3 / 2)
        self.static_tf.sendTransform(transform)
        deadline = time.monotonic() + 8
        while not any(msg.submap for msg in self.submaps) and time.monotonic() < deadline:
            self.pump(.1, imu_yaw)
            self.assertIsNone(self.process.poll(), self.log())
        self.assertTrue(any(msg.submap for msg in self.submaps), self.log())
        first = next(msg.submap[0] for msg in self.submaps if msg.submap)
        self.assertEqual(first.trajectory_id, 0)
        self.assertEqual(first.submap_index, 0)
        q = first.pose.orientation
        actual_yaw = math.atan2(2 * (q.w * q.z + q.x * q.y),
                                1 - 2 * (q.y * q.y + q.z * q.z))
        expected = imu_yaw - .3 + .2
        error = math.atan2(math.sin(actual_yaw - expected), math.cos(actual_yaw - expected))
        self.assertAlmostEqual(error, 0., delta=.03, msg=self.log())
        self.process.send_signal(signal.SIGINT)
        self.assertEqual(self.process.wait(timeout=15), 0, self.log())
        self.assertGreater((self.root / 'state.pbstream').stat().st_size, 0)

        # A saved map must retain its heading without requiring a compass on load.
        self.config.write_text(self.config.read_text().replace(
            'initialize_map_from_imu = true', 'initialize_map_from_imu = false'))
        self.submaps.clear()
        self.start(['-load_state_filename=' + str(self.root / 'state.pbstream'),
                    '-start_trajectory_with_default_topics=false'])
        deadline = time.monotonic() + 8
        while not any(msg.submap for msg in self.submaps) and time.monotonic() < deadline:
            rclpy.spin_once(self.node, timeout_sec=.1)
            self.assertIsNone(self.process.poll(), self.log())
        self.assertTrue(any(msg.submap for msg in self.submaps), self.log())
        loaded = next(msg.submap[0] for msg in self.submaps if msg.submap)
        self.assertAlmostEqual(loaded.pose.orientation.z, q.z, delta=.01)
        self.assertAlmostEqual(loaded.pose.orientation.w, q.w, delta=.01)

    def test_positive_heading_and_mounting_rotation(self):
        self.check_heading(1.2)

    def test_negative_heading_and_mounting_rotation(self):
        self.check_heading(-1.8)

    def test_disabled_mode_keeps_default_startup(self):
        self.config.write_text(self.config.read_text().replace(
            'initialize_map_from_imu = true', 'initialize_map_from_imu = false'))
        self.start()
        deadline = time.monotonic() + 8
        while not any(msg.submap for msg in self.submaps) and time.monotonic() < deadline:
            self.pump(.1)
            self.assertIsNone(self.process.poll(), self.log())
        self.assertTrue(any(msg.submap for msg in self.submaps), self.log())
        self.assertNotIn('Waiting for initial ENU', self.log())

    def test_timeout_does_not_start_a_trajectory(self):
        self.config.write_text(self.config.read_text().replace(
            'imu_heading_timeout_sec = 10.', 'imu_heading_timeout_sec = 0.5'))
        self.start()
        self.assertEqual(self.process.wait(timeout=8), 1, self.log())
        self.assertIn('no trajectory started', self.log())

    def test_saved_map_mode_is_rejected(self):
        self.start(['-load_state_filename=must_not_be_opened.pbstream'])
        self.assertEqual(self.process.wait(timeout=8), 1, self.log())
        self.assertIn('fresh 2D map', self.log())


if __name__ == '__main__':
    rclpy.init()
    try:
        unittest.main()
    finally:
        rclpy.shutdown()
