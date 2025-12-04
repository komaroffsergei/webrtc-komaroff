import logging
from aiortc import RTCPeerConnection
from typing import Dict, Any

logger = logging.getLogger("webrtc")


def attach_pc_lifecycle(
    pc: RTCPeerConnection,
    app: Dict[str, Any],
    graph,
    audio_transceiver,
    echo_ref: Dict[str, Any],
) -> None:
    """Attach connectionstatechange handler to RTCPeerConnection.

    Responsibilities:
    - Stop audio graph on terminal states (failed/closed/disconnected)
    - Stop echo node if present
    - Detach sender track
    - Remove pc from app set and close
    """

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        state = pc.connectionState
        logger.info(f"PC state changed: {state}")
        if state in ("failed", "closed", "disconnected"):
            logger.info("Stopping audio graph due to terminal/disconnected state")
            try:
                await graph.stop()
            except Exception:
                logger.exception("Error while stopping audio graph")
            # Stop echo node if present (synchronous stop)
            try:
                node = echo_ref.get("node")
                if node is not None:
                    node.stop()
            except Exception:
                logger.debug("Echo node stop failed", exc_info=True)
            # Detach sender track to free resources
            try:
                await audio_transceiver.sender.replaceTrack(None)
            except Exception:
                logger.debug("replaceTrack(None) failed or not needed", exc_info=True)
            # Remove PC from app set and close
            try:
                app["pcs"].discard(pc)
            except Exception:
                logger.debug("Failed to discard PC from app set", exc_info=True)
            if state != "closed":
                try:
                    await pc.close()
                except Exception:
                    logger.debug("PC close failed", exc_info=True)
