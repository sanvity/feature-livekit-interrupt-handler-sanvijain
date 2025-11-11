import logging
import weakref

from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    RoomOutputOptions,
    RunContext,
    WorkerOptions,
    cli,
    metrics,
)
from livekit.agents.llm import function_tool
from livekit.plugins import silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from extensions.filler_aware_adapter import FillerAwareAdapter

# To enable noise cancellation, uncomment the following:
# from livekit.plugins import noise_cancellation
# Use __name__ for a standard logger setup
logger = logging.getLogger(__name__)

load_dotenv()


class MyAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are a voice assistant named Kelly."
                "You will be interacting with users through voice."
                "Keep your responses concise and to the point."
                "Your responses must be plain text. Do not use markdown, emojis, or any special characters."
                "You should be curious, friendly, and have a sense of humor."
                "Always speak english to the user."
            )
        )

    async def on_enter(self):
        # When the agent first joins the session, generate an
        # initial reply based on the instructions.
        self.session.generate_reply()

    # Functions with the @function_tool decorator are exposed to the LLM
    @function_tool
    async def lookup_weather(
        self, context: RunContext, location: str, latitude: str, longitude: str
    ):
        """
        Provides weather information for a specific location.
        The user must provide a location (city or region).
        This function will estimate the latitude and longitude
        and not ask the user for them.

        Args:
            location: The city or region for the weather query.
            latitude: Estimated latitude (do not ask user).
            longitude: Estimated longitude (do not ask user).
        """

        logger.info(f"Received weather lookup for {location}")

        # This is a placeholder response
        return "sunny with a temperature of 70 degrees."


def prewarm(process: JobProcess):
    """
    Prewarms resources needed by the agent, like the VAD model.
    """
    process.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    """
    This is the main entrypoint for the agent job.
    """
    # Set up logging context
    ctx.log_context_fields = {
        "room": ctx.room.name,
        "job": ctx.job.id,
    }

    session = AgentSession(
        # LLM (Brain)
        llm="openai/gpt-4.1-mini",
        # STT (Ears)
        stt="assemblyai/universal-streaming:en",
        # TTS (Voice)
        tts="cartesia/sonic-2:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
        # VAD (Voice Activity Detection)
        vad=ctx.proc.userdata["vad"],
        turn_detection=MultilingualModel(unlikely_threshold=0.80),
        
        # Enable features
        preemptive_generation=True,
        resume_false_interruption=True,
        false_interruption_timeout=0.2,
    )

    # ============================================================
    # AGENT-SPEAKING DETECTION
    # ============================================================

    session_ref = weakref.ref(session)

    def is_agent_speaking_now():
        """
        Checks if the agent's TTS audio is currently playing.
        """
        current_session = session_ref()
        if not current_session:
            return False

        audio_output = getattr(current_session, "_audio_out", None)
        if audio_output and hasattr(audio_output, "is_speaking"):
            return bool(audio_output.is_speaking)

        return False

    # ============================================================
    # WRAP THE STT WITH FILLER-AWARE ADAPTER
    # ============================================================

    original_stt = session._stt
    session._stt = FillerAwareAdapter(original_stt, is_agent_speaking_now)

    # ============================================================
    # METRICS & USAGE LOGGING
    # ============================================================

    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(event: MetricsCollectedEvent):
        metrics.log_metrics(event.metrics)
        usage_collector.collect(event.metrics)

    async def log_final_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Final Usage Summary: {summary}")

    # Register shutdown callback
    ctx.add_shutdown_callback(log_final_usage)

    await session.start(
        agent=MyAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # Example:
            # noise_cancellation=noise_cancellation.BVC(),
        ),
        room_output_options=RoomOutputOptions(transcription_enabled=True),
    )


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        )
    )

    