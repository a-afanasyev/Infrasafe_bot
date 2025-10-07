"""
Bot Gateway Service - Distributed Tracing
UK Management Bot - Sprint 19-22

OpenTelemetry integration for distributed tracing with Jaeger.
"""

import logging
from typing import Optional

from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

logger = logging.getLogger(__name__)


def init_tracing(
    service_name: str,
    service_version: str,
    jaeger_host: str = "jaeger",
    jaeger_port: int = 6831,
    environment: str = "production",
    enabled: bool = True
) -> Optional[trace.Tracer]:
    """
    Initialize OpenTelemetry tracing with Jaeger exporter.

    Args:
        service_name: Name of the service
        service_version: Version of the service
        jaeger_host: Jaeger agent host
        jaeger_port: Jaeger agent port
        environment: Environment name
        enabled: Whether tracing is enabled

    Returns:
        Tracer instance if enabled, None otherwise
    """
    if not enabled:
        logger.info("Distributed tracing is disabled")
        return None

    try:
        # Create resource with service information
        resource = Resource.create({
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            "environment": environment,
            "service.namespace": "uk-management-bot"
        })

        # Create Jaeger exporter
        jaeger_exporter = JaegerExporter(
            agent_host_name=jaeger_host,
            agent_port=jaeger_port,
        )

        # Create tracer provider
        tracer_provider = TracerProvider(resource=resource)

        # Add span processor with Jaeger exporter
        span_processor = BatchSpanProcessor(jaeger_exporter)
        tracer_provider.add_span_processor(span_processor)

        # Set global tracer provider
        trace.set_tracer_provider(tracer_provider)

        # Instrument libraries
        instrument_libraries()

        # Get tracer
        tracer = trace.get_tracer(service_name, service_version)

        logger.info(f"✅ Distributed tracing initialized: {jaeger_host}:{jaeger_port}")
        return tracer

    except Exception as e:
        logger.error(f"❌ Failed to initialize tracing: {e}", exc_info=True)
        return None


def instrument_libraries():
    """
    Instrument common libraries for automatic tracing.

    Instruments:
    - aiohttp client (HTTP requests)
    - httpx (HTTP requests)
    - Redis operations
    - SQLAlchemy database queries
    """
    try:
        # Instrument aiohttp client
        AioHttpClientInstrumentor().instrument()
        logger.debug("Instrumented aiohttp client")

        # Instrument httpx
        HTTPXClientInstrumentor().instrument()
        logger.debug("Instrumented httpx")

        # Instrument Redis
        RedisInstrumentor().instrument()
        logger.debug("Instrumented Redis")

        # Note: SQLAlchemy instrumentation requires engine instance
        # Will be done separately when engine is created
        logger.debug("Library instrumentation complete")

    except Exception as e:
        logger.warning(f"Failed to instrument some libraries: {e}")


def instrument_sqlalchemy_engine(engine):
    """
    Instrument SQLAlchemy engine for tracing.

    Args:
        engine: SQLAlchemy engine instance
    """
    try:
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            enable_commenter=True,
        )
        logger.debug("Instrumented SQLAlchemy engine")
    except Exception as e:
        logger.warning(f"Failed to instrument SQLAlchemy: {e}")


def get_current_span() -> Optional[trace.Span]:
    """
    Get current active span.

    Returns:
        Current span if exists, None otherwise
    """
    return trace.get_current_span()


def add_span_attribute(key: str, value: any):
    """
    Add attribute to current span.

    Args:
        key: Attribute key
        value: Attribute value
    """
    span = get_current_span()
    if span and span.is_recording():
        span.set_attribute(key, value)


def add_span_event(name: str, attributes: Optional[dict] = None):
    """
    Add event to current span.

    Args:
        name: Event name
        attributes: Event attributes
    """
    span = get_current_span()
    if span and span.is_recording():
        span.add_event(name, attributes or {})


def record_exception(exception: Exception):
    """
    Record exception in current span.

    Args:
        exception: Exception to record
    """
    span = get_current_span()
    if span and span.is_recording():
        span.record_exception(exception)


def create_span(name: str, attributes: Optional[dict] = None) -> trace.Span:
    """
    Create a new span.

    Args:
        name: Span name
        attributes: Span attributes

    Returns:
        New span
    """
    tracer = trace.get_tracer(__name__)
    span = tracer.start_span(name)

    if attributes and span.is_recording():
        for key, value in attributes.items():
            span.set_attribute(key, value)

    return span
