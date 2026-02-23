"""
LiveAvatar + Ominis Clinical LLM — Pipecat agent.

Connects HeyGen LiveAvatar to Ominis 2.0 Clinic (BioMistral) via the
OpenAI-compatible proxy at /v1/liveavatar/chat/completions.

Entry point: async def bot(runner_args) for Pipecat Cloud.
Local run: python main.py (or python -m bot for Pipecat Cloud image)
"""

import os

import aiohttp
from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService, LiveOptions
from pipecat.transcriptions.language import Language
from pipecat.services.heygen.api_liveavatar import (
    AvatarPersona,
    LiveAvatarNewSessionRequest,
)
from pipecat.services.heygen.client import ServiceType
from pipecat.services.heygen.video import HeyGenVideoService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams, DailyTransport

load_dotenv(override=True)

CLINICAL_SYSTEM_PROMPT = """Eres un asistente médico de Ominis Health respaldado por FUNSALUD.
Responde en español de forma clara y breve. Evita emojis, listas con viñetas y caracteres especiales
que no se puedan pronunciar bien. Sé conciso porque tu respuesta se lee en voz alta.
No des diagnósticos médicos; recomienda consultar a un profesional cuando sea apropiado."""

transport_params = {
    "daily": lambda: DailyParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        video_out_enabled=True,
        video_out_is_live=True,
        video_out_width=1280,
        video_out_height=720,
        video_out_bitrate=2_000_000,
    ),
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        video_out_enabled=True,
        video_out_is_live=True,
        video_out_width=1280,
        video_out_height=720,
    ),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting Ominis LiveAvatar bot")
    base_url = os.getenv("OMINIS_BACKEND_URL", "http://localhost:8000/v1/liveavatar").rstrip("/")
    api_key = os.getenv("OMINIS_API_KEY", "")

    async with aiohttp.ClientSession() as session:
        stt = DeepgramSTTService(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            live_options=LiveOptions(language=Language.ES, smart_format=True),
        )

        # Voice: use CARTESIA_VOICE_ID for Spanish (e.g. Alessandra-like).
        # Default is a Spanish-capable female voice; override via env to match HeyGen's Alessandra.
        cartesia_voice = os.getenv("CARTESIA_VOICE_ID", "00967b2f-88a6-4a31-8153-110a92134b9f")
        tts = CartesiaTTSService(
            api_key=os.getenv("CARTESIA_API_KEY"),
            voice_id=cartesia_voice,
        )

        llm = OpenAILLMService(
            api_key=api_key or "dummy",
            base_url=base_url,
            model="ominis-2.0-med",
        )

        # Avatar: Marianne Sitting. Sandbox only allows Wayne; use is_sandbox=False for custom avatars.
        avatar_id = os.getenv("HEYGEN_AVATAR_ID", "bf00036b-558a-44b5-b2ff-1e3cec0f4ceb")
        is_sandbox = os.getenv("HEYGEN_SANDBOX", "false").lower() in ("1", "true", "yes")
        hey_gen = HeyGenVideoService(
            api_key=os.getenv("HEYGEN_LIVE_AVATAR_API_KEY"),
            service_type=ServiceType.LIVE_AVATAR,
            session=session,
            session_request=LiveAvatarNewSessionRequest(
                is_sandbox=is_sandbox,
                avatar_id=avatar_id,
                avatar_persona=AvatarPersona(
                    language="es",
                    voice_id=os.getenv("HEYGEN_VOICE_ID", "1bd001e7e50f421d891986aad0228f13"),  # Alessandra
                ),
            ),
        )

        messages = [{"role": "system", "content": CLINICAL_SYSTEM_PROMPT}]
        context = LLMContext(messages)
        user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
            context,
            user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
        )

        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                user_aggregator,
                llm,
                tts,
                hey_gen,
                transport.output(),
                assistant_aggregator,
            ]
        )

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
            idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        )

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info("Client connected")
            if isinstance(transport, DailyTransport):
                await transport.update_publishing(
                    publishing_settings={
                        "camera": {"sendSettings": {"allowAdaptiveLayers": True}}
                    }
                )
            messages.append({
                "role": "system",
                "content": "Saluda brevemente en español: 'Hola, soy el asistente de Ominis Health. ¿En qué puedo ayudarte?'",
            })
            await task.queue_frames([LLMRunFrame()])

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info("Client disconnected")
            await task.cancel()

        runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
        await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Entry point for Pipecat Cloud. Called by the platform."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
