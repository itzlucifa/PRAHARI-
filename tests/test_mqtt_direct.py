import paho.mqtt.client as mqtt
import time
import json

def on_connect(client, userdata, flags, rc, properties=None):
    print('MQTT connected, rc=%d' % rc)
    client.subscribe('fuse/events/all')

def on_message(client, userdata, msg):
    print('Received:', msg.payload.decode()[:80])

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect('localhost', 1883, 60)
client.loop_start()
print('Connecting...')
time.sleep(2)
event = json.dumps({'test': 'direct', 'event_id': 'mqtt-test-001'})
client.publish('fuse/events/all', event)
print('Published:', event)
time.sleep(2)
client.loop_stop()
client.disconnect()
print('Done')
