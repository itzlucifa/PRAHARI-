from amqtt.broker import Broker
import asyncio

config = {
    'listeners': {
        'default': {
            'type': 'tcp',
            'bind': '127.0.0.1:1883'
        }
    },
    'sys_interval': 0,
    'auth': {
        'allow-anonymous': True
    },
    'topic-check': {
        'enabled': False
    }
}

async def main():
    broker = Broker(config)
    await broker.start()
    print('MQTT broker ready on 127.0.0.1:1883')
    await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())
