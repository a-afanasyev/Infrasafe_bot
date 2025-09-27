# OpenTelemetry Tracing Middleware
# UK Management Bot - Microservices

import logging
from typing import Callable
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.semconv.resource import ResourceAttributes

from ..config import settings

logger = logging.getLogger(__name__)

class TracingMiddleware(BaseHTTPMiddleware):
    """OpenTelemetry tracing middleware"""

    def __init__(self, app):
        super().__init__(app)
        self.setup_tracing()

    def setup_tracing(self):
        """Initialize OpenTelemetry tracing"""
        try:
            # Create resource
            resource = Resource.create({
                ResourceAttributes.SERVICE_NAME: settings.service_name,
                ResourceAttributes.SERVICE_VERSION: settings.version,
                ResourceAttributes.SERVICE_NAMESPACE: "uk-management-bot",
            })

            # Set up tracer provider
            trace.set_tracer_provider(TracerProvider(resource=resource))
            tracer = trace.get_tracer(__name__)

            # Set up Jaeger exporter
            jaeger_exporter = JaegerExporter(
                agent_host_name="jaeger",
                agent_port=6831,
                collector_endpoint="http://jaeger:14268/api/traces",
            )

            # Set up OTLP exporter (for OpenTelemetry Collector)
            otlp_exporter = OTLPSpanExporter(
                endpoint=settings.otlp_endpoint,
                insecure=True
            )

            # Add span processors
            trace.get_tracer_provider().add_span_processor(
                BatchSpanProcessor(jaeger_exporter)
            )
            trace.get_tracer_provider().add_span_processor(
                BatchSpanProcessor(otlp_exporter)
            )

            logger.info("OpenTelemetry tracing initialized successfully")

        except Exception as e:
            logger.warning(f"Failed to initialize tracing: {e}")

    async def dispatch(self, request: Request, call_next: Callable):
        """Add tracing to HTTP requests"""
        tracer = trace.get_tracer(__name__)

        with tracer.start_as_current_span(
            f"{request.method} {request.url.path}",
            attributes={
                "http.method": request.method,
                "http.url": str(request.url),
                "http.scheme": request.url.scheme,
                "http.host": request.url.hostname,
                "http.target": request.url.path,
                "user_agent.original": request.headers.get("user-agent", ""),
            }
        ) as span:
            try:
                response = await call_next(request)

                # Add response attributes
                span.set_attributes({
                    "http.status_code": response.status_code,
                    "http.response.size": response.headers.get("content-length", "0"),
                })

                # Mark as error if status code >= 400
                if response.status_code >= 400:
                    span.set_status(trace.Status(trace.StatusCode.ERROR))

                return response

            except Exception as e:
                # Record exception
                span.record_exception(e)
                span.set_status(
                    trace.Status(trace.StatusCode.ERROR, str(e))
                )
                raise

def instrument_app(app):
    """Instrument FastAPI app with OpenTelemetry"""
    try:
        # Instrument FastAPI
        FastAPIInstrumentor.instrument_app(app, tracer_provider=trace.get_tracer_provider())

        # Instrument SQLAlchemy
        SQLAlchemyInstrumentor().instrument()

        # Instrument Redis
        RedisInstrumentor().instrument()

        # Instrument HTTP requests
        RequestsInstrumentor().instrument()

        logger.info("Application instrumentation completed")

    except Exception as e:
        logger.warning(f"Failed to instrument application: {e}")

def get_tracer():
    """Get OpenTelemetry tracer"""
    return trace.get_tracer(__name__)

def add_span_attributes(span, **attributes):
    """Add attributes to current span"""
    if span and span.is_recording():
        span.set_attributes(attributes)

def record_exception(exception: Exception):
    """Record exception in current span"""
    span = trace.get_current_span()
    if span and span.is_recording():
        span.record_exception(exception)
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(exception)))