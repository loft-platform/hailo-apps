"""
Common utilities and constants for GStreamer applications.
"""
import sys
import cv2
import gi
from gi.repository import GLib, GObject, Gst
from hailo_apps.python.core.common.hailo_logger import get_logger

hailo_logger = get_logger(__name__)

# Watchdog constants
WATCHDOG_TIMEOUT = 5  # seconds
WATCHDOG_INTERVAL = 5  # seconds

_suppressed_gstreamer_patterns = ["write map requested on non-writable buffer"]

def gstreamer_log_filter(log_domain, log_level, message, user_data):
    if message and not any(pattern in message for pattern in _suppressed_gstreamer_patterns):
        if log_level & (GLib.LogLevelFlags.LEVEL_ERROR | GLib.LogLevelFlags.LEVEL_CRITICAL):
            sys.stderr.write(f"({log_domain}): CRITICAL: {message}\n")
            sys.stderr.flush()

def disable_qos(pipeline):
    """
    Disables QoS on all elements in the pipeline.
    Safely handles Hailo elements that may segfault on GObject.list_properties().
    """
    hailo_logger.debug("disable_qos() called")
    if not isinstance(pipeline, Gst.Pipeline):
        hailo_logger.error("Provided object is not a GStreamer Pipeline")
        return

    it = pipeline.iterate_elements()
    while True:
        try:
            result, element = it.next()
            if result != Gst.IteratorResult.OK:
                break
            try:
                props = [p.name for p in GObject.list_properties(element)]
                if "qos" in props:
                    element.set_property("qos", False)
                    hailo_logger.debug(f"Set qos=False for {element.get_name()}")
            except Exception as e:
                hailo_logger.debug(f"Skipping qos for {element.get_name()}: {e}")
        except Exception as e:
            hailo_logger.debug(f"Iterator error in disable_qos: {e}")
            break

def display_user_data_frame(user_data):
    hailo_logger.debug("display_user_data_frame() started")
    while user_data.running:
        frame = user_data.get_frame()
        if frame is not None:
            cv2.imshow("User Frame", frame)
        cv2.waitKey(1)
    hailo_logger.debug("display_user_data_frame() exiting")
    cv2.destroyAllWindows()