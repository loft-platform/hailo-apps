# region imports
# Standard library imports
import datetime
import time
from datetime import datetime
import os
import json
import uuid
import paho.mqtt.client as mqtt
os.environ["GST_PLUGIN_FEATURE_RANK"] = "vaapidecodebin:NONE"

# Third-party imports
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

# Local application-specific imports
import hailo
from hailo_apps.python.core.common.hailo_logger import get_logger
from hailo_apps.python.core.gstreamer.gstreamer_app import app_callback_class
from hailo_apps.python.pipeline_apps.face_recognition.face_recognition_pipeline import GStreamerFaceRecognitionApp
from hailo_apps.python.core.common.telegram_handler import TelegramHandler

hailo_logger = get_logger(__name__)
# endregion imports

MQTT_ENABLED = True
MQTT_BROKER = "192.168.8.239"      
MQTT_PORT = 1883
MQTT_TOPIC = "LYT/AI/CCTV/DETECTION"
MQTT_USERNAME = "admin"
MQTT_PASSWORD = "admin@123"
MQTT_PROTOCOL = "mqtt"
LIGHT_TOPIC = "LYT/AI/SCENE/EXECUTE"

LIGHT_PREFERENCES = {
    "abhay": {"scene_name": "Movie", "scene_number": 43927},
    "shraddha": {"scene_name": "Party ","scene_number": 14051},
    "jagdish": {"scene_name": "Home","scene_number": 36534},
    "vishal": {"scene_name": "On lights","scene_number": 64282},
    "deepam": {"scene_name": "Warm white","scene_number": 63196},
    "hiral": {"scene_name": "OFF LIGHTS","scene_number": 634951},
    "ghanshyam": {"scene_name": "Switch off","scene_number": 46185}
}

class user_callbacks_class(app_callback_class):
    def __init__(self):
        super().__init__()
        self.frame = None
        self.latest_track_id = -1

        self.mqtt_enabled = MQTT_ENABLED
        self.last_sent = {}
        self.last_logged = {}
        self.last_unknown_sent = 0
        self.last_known_name = None
        self.last_name_sent = {}
        self.last_known_time = 0
        self.camera_role = "door"
        self.last_light_trigger = {}
        self.device_mac = ':'.join([
            f'{(uuid.getnode() >> ele) & 0xff:02x}'
            for ele in range(40, -8, -8)
        ])
        self.mqtt_client = None
        if self.mqtt_enabled:
            self.mqtt_client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="face_recognition"
            )
            self.mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
            if MQTT_PROTOCOL == "mqtts":
             self.mqtt_client.tls_set()
            self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.mqtt_client.loop_start()
            import time
            time.sleep(1) 

    def send_notification(self, name, global_id, confidence, frame):
        if not self.mqtt_enabled or self.mqtt_client is None:
            return

        now = datetime.now().timestamp()
        # remember recently recognized known person
        if str(name).lower() != "unknown":
            self.last_known_name = str(name)
            self.last_known_time = now
        else:
            # ignore unknown if a known person was detected in last 5 seconds
            if now - self.last_known_time < 2:
                return

            # send only one unknown alert every 15 seconds
            if now - self.last_unknown_sent < 15:
                return

            self.last_unknown_sent = now   
        # -------- NEW: name-based cooldown --------
        name_key = str(name).lower()

        if name_key != "unknown":
            if (
                name_key in self.last_name_sent and
                now - self.last_name_sent[name_key] < 10
            ):
                return

            self.last_name_sent[name_key] = now
        # -----------------------------------------
        # avoid sending the same person repeatedly every frame
        if global_id in self.last_sent:
            if now - self.last_sent[global_id] < 5:
                return

        payload = {
            "device_mac": self.device_mac,
            "device_type": "camera",
            "zone_name": "Entry zone",
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "track_ids": [int(global_id)],
            "faces": [str(name)],
            "security_alert": str(name).lower() == "unknown" ,
            "message": (
                f"Unknown person detected in { 'Entry zone' }"
                if str(name).lower() == "unknown"
                else f"{name} detected in { 'Entry zone' }"
            )
        }

        # ================= DOOR CAMERA =================
        if self.camera_role == "door":

            self.mqtt_client.publish(MQTT_TOPIC, json.dumps(payload))
            print(f"[DOOR] {payload}")

        # ================= LIGHT CAMERA =================
        elif self.camera_role == "light":

            if name_key != "unknown" and name_key in LIGHT_PREFERENCES:

                if name_key not in self.last_light_trigger or \
                now - self.last_light_trigger[name_key] >= 10:

                    self.last_light_trigger[name_key] = now

                    light_data = LIGHT_PREFERENCES[name_key]

                    light_payload = {
                        "person": name_key,
                        "scene_number": light_data["scene_number"]
                    }

                    result = self.mqtt_client.publish(LIGHT_TOPIC, json.dumps(light_payload))
                    print(f"[LIGHT MQTT] topic={LIGHT_TOPIC}, rc={result.rc}")

       
        self.last_sent[global_id] = now


def app_callback(element, buffer, user_data):
    # Note: Frame counting is handled automatically by the framework wrapper
    if buffer is None:
        hailo_logger.warning("Received None buffer.")
        return
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)
    current_people = set()
    for detection in detections:
        label = detection.get_label()
        detection_confidence = detection.get_confidence()
        if label == "face":
            track_id = 0
            track = detection.get_objects_typed(hailo.HAILO_UNIQUE_ID)
            if len(track) > 0:
                track_id = track[0].get_id()
            string_to_print = f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]: Face detection ID: {track_id} (Confidence: {detection_confidence:.1f}), '
            classifications = detection.get_objects_typed(hailo.HAILO_CLASSIFICATION)
            if len(classifications) > 0:
                classification = classifications[0]

                if classification.get_label() == 'Unknown':
                    recognized_name = 'Unknown'
                    string_to_print += 'Unknown person detected'
                else:
                    recognized_name = classification.get_label()
                    string_to_print += (
                        f'Person recognition: {recognized_name} '
                        f'(Confidence: {classification.get_confidence():.1f})'
                    )

                now = time.time()

                if not hasattr(user_data, "last_logged"):
                    user_data.last_logged = set()

                if track_id not in user_data.last_logged:
                    print(string_to_print)
                    user_data.last_logged.add(track_id)
    active_track_ids = set()

    for detection in detections:
        if detection.get_label() == "face":
            track = detection.get_objects_typed(hailo.HAILO_UNIQUE_ID)
            if len(track) > 0:
                active_track_ids.add(track[0].get_id())

    if hasattr(user_data, "last_logged"):
        user_data.last_logged = {
            tid for tid in user_data.last_logged
            if tid in active_track_ids
        }

    return
              


def main():
    hailo_logger.info("Starting Face Recognition App.")
    user_data = user_callbacks_class()
    # detect camera role from input (IMPORTANT)
    input_source = ""
    for i, arg in enumerate(os.sys.argv):
        if arg == "--input" and i + 1 < len(os.sys.argv):
            input_source = os.sys.argv[i + 1]

    if "192.168.8.78" in input_source:
        user_data.camera_role = "door"

    elif "192.168.8.79" in input_source:
        user_data.camera_role = "light"

    print(f"[CAMERA ROLE] {user_data.camera_role}")

    pipeline = GStreamerFaceRecognitionApp(app_callback, user_data)
    if pipeline.options_menu.mode == 'delete':
        pipeline.db_handler.clear_table()
        exit(0)
    elif pipeline.options_menu.mode == 'train':
        pipeline.run()
        exit(0)
    else:  # 'run' mode
        pipeline.run()


if __name__ == "__main__":
    main()
