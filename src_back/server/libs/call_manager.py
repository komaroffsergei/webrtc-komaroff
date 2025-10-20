import asyncio
import ipaddress
import logging
import os
import socket
import time
from typing import Optional

from aioice import Candidate, turn
from aioice.candidate import candidate_foundation, candidate_priority
from aioice.ice import StunProtocol, TransportPolicy, server_reflexive_candidate, relayed_candidate
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceGatherer, RTCIceServer
from aiortc.rtcicetransport import Connection
from ..processors.graph import AudioGraph
from ..processors import TrackSourceNode, EchoTrackNode, LossFillerNode, RecorderNode, BgmMixerNode
from ..utils.config import STATIC_DIR
from ..utils.pc_lifecycle import attach_pc_lifecycle

logger = logging.getLogger("webrtc")

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


class CallManager:
    def __init__(self, app):
        self.app = app
        RTCIceGatherer.getDefaultIceServers = getDefaultIceServers
        Connection.get_component_candidates = get_component_candidates

    async def establish_connection(self, pc, offer):
        t0 = time.monotonic()
        await pc.setRemoteDescription(offer)
        t_set_remote = time.monotonic()
        answer = await pc.createAnswer()
        t_create_answer = time.monotonic()
        await pc.setLocalDescription(answer)
        t_set_local = time.monotonic()
        logger.info(
            "offer_timing: setRemote=%.2fms createAnswer=%.2fms setLocal=%.2fms",
            (t_set_remote - t0) * 1000,
            (t_create_answer - t_set_remote) * 1000,
            (t_set_local - t_create_answer) * 1000,
        )


        while getattr(pc, "iceGatheringState", None) != "complete":
            await asyncio.sleep(0.05)

        return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

    async def start_audio_pipeline(self, graph, track, audio_transceiver, echo_ref):
        source = graph.add(TrackSourceNode(
            track,
            frame_duration_ms=20,
            target_rate=48000,
            target_channels=1,
            target_output_format='s16'
        ))

        bgm = graph.add(BgmMixerNode(source, bgm_path=os.path.join(STATIC_DIR, "bg.wav"), gain=0.2))
        filler = graph.add(LossFillerNode(source, latency_budget_ms=180, backlog_leave_frames=2, fill_mode="silence"))
        recorder = graph.add(RecorderNode(filler, batch_frames=512))

        echo = EchoTrackNode(bgm)
        audio_transceiver.sender.replaceTrack(echo)
        echo_ref["node"] = echo
        asyncio.create_task(graph.start())

    async def handle_offer(self, params):
        sdp = params.get("sdp")
        offer_type = params.get("type")
        offer = RTCSessionDescription(sdp=sdp, type=offer_type)

        t_create_start = time.monotonic()
        pc = RTCPeerConnection()
        t_pc_created = time.monotonic()
        audio_transceiver = pc.addTransceiver("audio", direction="sendrecv")
        t_transceiver_added = time.monotonic()
        logger.info(
            "offer_timing_pc: create=%.2fms addTransceiver=%.2fms",
            (t_pc_created - t_create_start) * 1000,
            (t_transceiver_added - t_pc_created) * 1000,
        )

        pcs = {p for p in self.app["pcs"] if p.connectionState not in ("failed", "closed")}
        self.app["pcs"] = pcs
        pcs.add(pc)

        logger.info("PC created and audio transceiver added (sendrecv)")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Active PCs: {len(pcs)}")

        echo_ref = {"node": None}

        @pc.on("track")
        async def on_track(track):
            logger.info(f"on_track: received kind={track.kind}")
            if track.kind == "audio":
                graph = AudioGraph()
                attach_pc_lifecycle(pc, self.app, graph, audio_transceiver, echo_ref)
                await self.start_audio_pipeline(graph, track, audio_transceiver, echo_ref)
                logger.info("Audio graph started")

        try:
            resp = await self.establish_connection(pc, offer)
            return resp, None
        except Exception:
            logger.error("Failed to process SDP offer", exc_info=True)
            try:
                await audio_transceiver.sender.replaceTrack(None)
            except Exception:
                logger.debug("replaceTrack(None) failed or not needed", exc_info=True)
            await pc.close()
            return None, "failed to process offer"
