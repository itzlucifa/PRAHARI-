import paho.mqtt.client as mqtt
import json
import time
import threading

received = []

def on_connect(client, userdata, flags, rc, properties=None):
    print('Subscriber connected, rc=%s' % rc)
    client.subscribe('fuse/events/all')

def on_message(client, userdata, msg):
    received.append(msg.payload.decode())
    print('Received:', msg.payload.decode()[:80])

# Start subscriber in background
sub_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
sub_client.on_connect = on_connect
sub_client.on_message = on_message
sub_client.connect('localhost', 1883, 60)
sub_client.loop_start()

time.sleep(2)

# Publish from main thread
pub_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
pub_client.connect('localhost', 1883, 60)
pub_client.loop_start()
event = json.dumps({'event_id': 'direct-test', 'camera_id': 'camera-01', 'event_type': 'detection'})
pub_client.publish('fuse/events/all', event)
print('Published:', event)

time.sleep(3)
pub_client.loop_stop()
pub_client.disconnect()
sub_client.loop_stop()
sub_client.disconnect()
print('Total received:', len(received))
