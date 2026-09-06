import asyncio
import logging
import signal
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mqtt-broker")


class MQTTBroker:
    def __init__(self, host="0.0.0.0", port=1883):
        self.host = host
        self.port = port
        self.clients = {}
        self.subscriptions = {}
        self.server = None

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        client_id = f"client-{id(writer)}"
        client = {"id": client_id, "reader": reader, "writer": writer, "subs": set()}
        self.clients[client_id] = client
        logger.info("Client connected: %s", client_id)
        try:
            while True:
                packet = await self._read_packet(reader)
                if packet is None:
                    break
                packet_type, payload = packet
                logger.debug("Received packet type %d, payload len %d", packet_type, len(payload))
                await self._handle_packet(client, packet_type, payload)
        except Exception as exc:
            logger.debug("Client %s error: %s", client_id, exc)
        finally:
            await self._cleanup_client(client)
            logger.info("Client disconnected: %s", client_id)

    async def _read_packet(self, reader: asyncio.StreamReader):
        try:
            first = await reader.read(1)
            if not first:
                return None
            packet_type = first[0] >> 4
            remaining_len = 0
            mul = 1
            while True:
                byte = await reader.read(1)
                if not byte:
                    return None
                remaining_len += (byte[0] & 0x7F) * mul
                mul *= 128
                if not (byte[0] & 0x80):
                    break
            payload = b""
            if remaining_len > 0:
                payload = await reader.read(remaining_len)
            logger.debug("Read packet type=%d remaining=%d payload=%s", packet_type, remaining_len, payload[:50])
            return packet_type, payload
        except Exception as exc:
            logger.debug("Read packet error: %s", exc)
            return None

    def _encode_remaining_length(self, length: int) -> bytes:
        buf = bytearray()
        while length > 0:
            enc = length % 128
            length //= 128
            if length > 0:
                enc |= 0x80
            buf.append(enc)
        return bytes(buf)

    async def _send_packet(self, writer: asyncio.StreamWriter, packet_type: int, payload: bytes = b""):
        buf = bytearray()
        buf.append(packet_type << 4)
        buf.extend(self._encode_remaining_length(len(payload)))
        buf.extend(payload)
        writer.write(bytes(buf))
        await writer.drain()
        logger.debug("Sent packet type=%d payload_len=%d", packet_type, len(payload))

    async def _handle_packet(self, client, packet_type: int, payload: bytes):
        if packet_type == 1:  # CONNECT
            try:
                proto_len = (payload[0] << 8) | payload[1]
                payload_offset = 2 + proto_len + 4
                cid_len = (payload[payload_offset] << 8) | payload[payload_offset + 1]
                client_id_raw = payload[payload_offset + 2: payload_offset + 2 + cid_len]
                parsed_id = client_id_raw.decode("utf-8", errors="replace")
                if parsed_id:
                    old_key = client["id"]
                    if old_key in self.clients:
                        del self.clients[old_key]
                    client["id"] = parsed_id
                    self.clients[parsed_id] = client
            except Exception:
                pass
            await self._send_packet(client["writer"], 2, bytes([0x00, 0x00]))  # CONNACK
            logger.info("Client connected: %s", client["id"])

        elif packet_type == 3:  # PUBLISH
            topic_len = (payload[0] << 8) | payload[1]
            topic = payload[2:2 + topic_len].decode("utf-8", errors="replace")
            message = payload[2 + topic_len:]
            logger.info("Publish on %s from %s, msg_len=%d", topic, client["id"], len(message))
            await self._forward_publish(topic, message)

        elif packet_type == 8:  # SUBSCRIBE
            logger.debug("SUBSCRIBE payload: %s", payload.hex())
            if len(payload) >= 4:
                packet_id = (payload[0] << 8) | payload[1]
                topic_len = (payload[2] << 8) | payload[3]
                topic = payload[4:4 + topic_len].decode("utf-8", errors="replace")
                client["subs"].add(topic)
                self.subscriptions.setdefault(topic, set()).add(client["id"])
                logger.info("Client %s subscribed to %s", client["id"], topic)
                await self._send_packet(client["writer"], 9, bytes([(packet_id >> 8) & 0xFF, packet_id & 0xFF, 0x00]))  # SUBACK

        elif packet_type == 12:  # PINGREQ
            await self._send_packet(client["writer"], 13)  # PINGRESP

        elif packet_type == 14:  # DISCONNECT
            raise ConnectionResetError("Client disconnected")

    async def _forward_publish(self, topic: str, message: bytes):
        topic_bytes = topic.encode("utf-8")
        var_header = bytes([len(topic_bytes) >> 8, len(topic_bytes) & 0xFF]) + topic_bytes
        payload = var_header + message
        packet = bytes([0x30]) + self._encode_remaining_length(len(payload)) + payload
        subscribers = [self.clients[cid] for cid in self.subscriptions.get(topic, []) if cid in self.clients]
        logger.info("Forwarding to %d subscribers on %s", len(subscribers), topic)
        for sub_client in subscribers:
            try:
                sub_client["writer"].write(packet)
                await sub_client["writer"].drain()
                logger.debug("Forwarded to %s", sub_client["id"])
            except Exception as exc:
                logger.debug("Forward error to %s: %s", sub_client["id"], exc)

    async def _cleanup_client(self, client):
        client_id = client["id"]
        self.clients.pop(client_id, None)
        for topic in client["subs"]:
            self.subscriptions.get(topic, set()).discard(client_id)
        try:
            client["writer"].close()
            await client["writer"].wait_closed()
        except Exception:
            pass

    async def start(self):
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logger.info("MQTT broker listening on %s:%d", self.host, self.port)
        async with self.server:
            await self.server.serve_forever()

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()


async def main():
    broker = MQTTBroker()
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutting down broker...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            signal.signal(sig, lambda s, f: _signal_handler())

    server_task = asyncio.create_task(broker.start())
    await stop_event.wait()
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass
    await broker.stop()
    logger.info("Broker stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
