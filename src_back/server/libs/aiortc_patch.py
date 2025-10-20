import asyncio
import ipaddress
import socket
from typing import Optional

from aioice import Candidate, turn
from aioice.candidate import candidate_foundation, candidate_priority
from aioice.ice import StunProtocol, TransportPolicy, server_reflexive_candidate, relayed_candidate
from aiortc import RTCIceServer


def getDefaultIceServers(self):
    return [RTCIceServer("stun:stun.gis-master.ru:3478")]

async def get_component_candidates(
    self, component: int, addresses: list[str], timeout: int = 2
) -> list[Candidate]:
    candidates = []
    loop = asyncio.get_event_loop()

    # gather host candidates
    host_protocols = []
    for address in addresses:
        # create transport
        try:
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: StunProtocol(self), local_addr=(address, 0)
            )
            sock = transport.get_extra_info("socket")
            if sock is not None:
                sock.setsockopt(
                    socket.SOL_SOCKET, socket.SO_RCVBUF, turn.UDP_SOCKET_BUFFER_SIZE
                )
        except OSError as exc:
            self.__log_info("Could not bind to %s - %s", address, exc)
            continue
        host_protocols.append(protocol)

        # add host candidate
        candidate_address = protocol.transport.get_extra_info("sockname")
        protocol.local_candidate = Candidate(
            foundation=candidate_foundation("host", "udp", candidate_address[0]),
            component=component,
            transport="udp",
            priority=candidate_priority(component, "host"),
            host=candidate_address[0],
            port=candidate_address[1],
            type="host",
        )
        if self._transport_policy == TransportPolicy.ALL:
            candidates.append(protocol.local_candidate)
    self._protocols += host_protocols

    tasks: list[asyncio.Task[tuple[Candidate, Optional[StunProtocol]]]] = []

    # Query STUN server for server-reflexive candidates (IPv4 only).
    if self.stun_server:
        for protocol in host_protocols:
            if ipaddress.ip_address(protocol.local_candidate.host).version == 4:
                tasks.append(
                    asyncio.create_task(
                        server_reflexive_candidate(protocol, self.stun_server)
                    )
                )

    # Connect to TURN server.
    if self.turn_server:
        tasks.append(
            asyncio.create_task(
                relayed_candidate(
                    component=component,
                    protocol_factory=lambda: StunProtocol(self),
                    turn_server=self.turn_server,
                    turn_username=self.turn_username,
                    turn_password=self.turn_password,
                    turn_ssl=self.turn_ssl,
                    turn_transport=self.turn_transport,
                )
            )
        )

    # Run tasks in parallel and handle exceptions.
    if len(tasks):
        done, pending = await asyncio.wait(tasks, timeout=timeout)
        for task in done:
            if task.exception() is None:
                candidate, protocol = task.result()
                candidates.append(candidate)
                if protocol is not None:
                    self._protocols.append(protocol)
        for task in pending:
            task.cancel()

    return candidates