# import asyncio
# import ipaddress
# import logging
# import os
# import socket
# from typing import Optional, Any
#
# # Patch only aioice.IceTransport.get_component_candidates with full duplication
# # and configurable timeouts via environment variables.
# #
# # ENV (optional):
# # - AIOICE_COMPONENT_TIMEOUT_MS: overrides wait timeout in milliseconds
# # - AIOICE_COMPONENT_TIMEOUT_S: overrides wait timeout in seconds (used if MS not set)
#
# logger = logging.getLogger("webrtc")
#
#
# def _resolve_component_timeout(user_timeout) -> float:
#     # Highest priority: explicit env override
#     env_ms = os.getenv("AIOICE_COMPONENT_TIMEOUT_MS")
#     if env_ms:
#         try:
#             return max(0.05, float(env_ms) / 1000.0)
#         except Exception:
#             logger.warning("boot_patch: bad AIOICE_COMPONENT_TIMEOUT_MS=%r", env_ms)
#     env_s = os.getenv("AIOICE_COMPONENT_TIMEOUT_S")
#     if env_s:
#         try:
#             return max(0.05, float(env_s))
#         except Exception:
#             logger.warning("boot_patch: bad AIOICE_COMPONENT_TIMEOUT_S=%r", env_s)
#
#     # Fallback to value provided by caller (library default is 5 seconds)
#     try:
#         return max(0.05, float(user_timeout))
#     except Exception:
#         return 5.0
#
#
# def apply():  # side-effect patch
#     # 1) Patch aiortc.rtcicetransport.getDefaultIceServers with exact duplication
#     try:
#         from aiortc.rtcicetransport import RTCIceTransport, RTCIceServer
#
#         def _patched_getDefaultIceServers(cls) -> list:
#             return [RTCIceServer("stun:stun.l.google.com:19302")]
#
#         RTCIceTransport.getDefaultIceServers = classmethod(_patched_getDefaultIceServers)  # type: ignore[attr-defined]
#         logger.info("boot_patch: patched aiortc.RTCIceTransport.getDefaultIceServers")
#     except Exception as e:
#         logger.warning("boot_patch: failed to patch aiortc getDefaultIceServers: %s", e)
#
#     # 2) Patch aioice.IceTransport.get_component_candidates with full duplication and timeout control
#     try:
#         import importlib
#         ice = importlib.import_module("aioice.ice")
#         turn = importlib.import_module("aioice.turn")
#         IceTransport = getattr(ice, "IceTransport", None)
#         StunProtocol = getattr(ice, "StunProtocol", None)
#         TransportPolicy = getattr(ice, "TransportPolicy", None)
#         candidate_foundation = getattr(ice, "candidate_foundation", None)
#         candidate_priority = getattr(ice, "candidate_priority", None)
#         relayed_candidate = getattr(ice, "relayed_candidate", None)
#         server_reflexive_candidate = getattr(ice, "server_reflexive_candidate", None)
#         CandidateClass = getattr(ice, "Candidate", None)
#     except Exception as e:
#         logger.warning("boot_patch: failed to import aioice symbols, cannot patch get_component_candidates: %s", e, exc_info=True)
#         return
#
#     if not all([IceTransport, StunProtocol, TransportPolicy, candidate_foundation, candidate_priority, relayed_candidate, server_reflexive_candidate, CandidateClass]):
#         logger.warning("boot_patch: aioice symbols missing; skipping get_component_candidates patch")
#         return
#
#     orig = getattr(IceTransport, "get_component_candidates", None)
#     if orig is None:
#         logger.info("boot_patch: aioice.IceTransport.get_component_candidates not found; skipping")
#         return
#
#     async def patched_get_component_candidates(self, component: int, addresses: list[str], timeout: int = 5):
#         # Full duplication of upstream logic with controlled timeout
#         candidates = []
#         loop = asyncio.get_event_loop()
#
#         # gather host candidates
#         host_protocols = []
#         for address in addresses:
#             # create transport
#             try:
#                 transport, protocol = await loop.create_datagram_endpoint(
#                     lambda: StunProtocol(self), local_addr=(address, 0)
#                 )
#                 sock = transport.get_extra_info("socket")
#                 if sock is not None:
#                     sock.setsockopt(
#                         socket.SOL_SOCKET, socket.SO_RCVBUF, turn.UDP_SOCKET_BUFFER_SIZE
#                     )
#             except OSError as exc:
#                 self.__log_info("Could not bind to %s - %s", address, exc)
#                 continue
#             host_protocols.append(protocol)
#
#             # add host candidate
#             candidate_address = protocol.transport.get_extra_info("sockname")
#             protocol.local_candidate = self.Candidate(
#                 foundation=candidate_foundation("host", "udp", candidate_address[0]),
#                 component=component,
#                 transport="udp",
#                 priority=candidate_priority(component, "host"),
#                 host=candidate_address[0],
#                 port=candidate_address[1],
#                 type="host",
#             )
#             if self._transport_policy == TransportPolicy.ALL:
#                 candidates.append(protocol.local_candidate)
#         self._protocols += host_protocols
#
#         tasks: list[asyncio.Task[tuple["Candidate", Optional[StunProtocol]]]] = []  # type: ignore[name-defined]
#
#         # Query STUN server for server-reflexive candidates (IPv4 only).
#         if self.stun_server:
#             for protocol in host_protocols:
#                 if ipaddress.ip_address(protocol.local_candidate.host).version == 4:
#                     tasks.append(
#                         asyncio.create_task(
#                             server_reflexive_candidate(protocol, self.stun_server)
#                         )
#                     )
#
#         # Connect to TURN server.
#         if self.turn_server:
#             tasks.append(
#                 asyncio.create_task(
#                     relayed_candidate(
#                         component=component,
#                         protocol_factory=lambda: StunProtocol(self),
#                         turn_server=self.turn_server,
#                         turn_username=self.turn_username,
#                         turn_password=self.turn_password,
#                         turn_ssl=self.turn_ssl,
#                         turn_transport=self.turn_transport,
#                     )
#                 )
#             )
#
#         # Run tasks in parallel and handle exceptions.
#         if len(tasks):
#             wait_timeout = 1
#             done, pending = await asyncio.wait(tasks, timeout=wait_timeout)
#             for task in done:
#                 if task.exception() is None:
#                     candidate, protocol = task.result()
#                     candidates.append(candidate)
#                     if protocol is not None:
#                         self._protocols.append(protocol)
#             for task in pending:
#                 task.cancel()
#
#         return candidates
#
#     # Monkeypatch
#     setattr(IceTransport, "get_component_candidates", patched_get_component_candidates)
#     logger.info("boot_patch: patched aioice.IceTransport.get_component_candidates with env-configurable timeout")
#
#
# # Apply immediately on import
# apply()
