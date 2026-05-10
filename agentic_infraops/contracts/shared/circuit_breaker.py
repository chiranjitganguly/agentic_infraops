"""Circuit breaker decorator for GCP API calls (PLR-002).

Wraps the `circuitbreaker` library:
- Opens after 5 consecutive failures
- Half-opens after 60 seconds
- Exposes state as a Prometheus gauge per (tool, resource_type)
- Raises CircuitOpenError when the circuit is open
"""
from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from circuitbreaker import CircuitBreakerError, circuit

from agentic_infraops.contracts.shared.metrics import circuit_breaker_state

_logger = logging.getLogger(__name__)

_STATE_CLOSED = 0
_STATE_HALF_OPEN = 1
_STATE_OPEN = 2

F = TypeVar("F", bound=Callable[..., Any])


class CircuitOpenError(Exception):
    """Raised when an attempt is made to call a GCP API through an open circuit."""


def gcp_circuit_breaker(
    tool: str,
    resource_type: str = "unknown",
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    expected_exception: type[Exception] = Exception,
) -> Callable[[F], F]:
    """Decorator that wraps a GCP API function with a circuit breaker.

    Args:
        tool: Logical tool name (e.g. 'create_vm'). Used as Prometheus label.
        resource_type: GCP resource type label for Prometheus (e.g. 'compute_instance').
        failure_threshold: Consecutive failures before opening the circuit.
        recovery_timeout: Seconds to wait in open state before trying half-open.
        expected_exception: Exception type that counts as a circuit failure.
    """
    def decorator(func: F) -> F:
        # Apply the circuitbreaker library decorator
        breaker = circuit(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            expected_exception=expected_exception,
            name=f"{tool}_{resource_type}",
        )
        wrapped = breaker(func)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            _update_state_metric(tool, resource_type, wrapped)
            try:
                result = await wrapped(*args, **kwargs)
                _update_state_metric(tool, resource_type, wrapped)
                return result
            except CircuitBreakerError as exc:
                circuit_breaker_state.labels(tool=tool, resource_type=resource_type).set(_STATE_OPEN)
                _logger.warning(
                    "Circuit breaker open",
                    extra={"tool": tool, "resource_type": resource_type},
                )
                raise CircuitOpenError(
                    f"Circuit breaker for '{tool}' ({resource_type}) is open — GCP API call blocked"
                ) from exc

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            _update_state_metric(tool, resource_type, wrapped)
            try:
                result = wrapped(*args, **kwargs)
                _update_state_metric(tool, resource_type, wrapped)
                return result
            except CircuitBreakerError as exc:
                circuit_breaker_state.labels(tool=tool, resource_type=resource_type).set(_STATE_OPEN)
                _logger.warning(
                    "Circuit breaker open",
                    extra={"tool": tool, "resource_type": resource_type},
                )
                raise CircuitOpenError(
                    f"Circuit breaker for '{tool}' ({resource_type}) is open — GCP API call blocked"
                ) from exc

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator


def _update_state_metric(tool: str, resource_type: str, wrapped: Any) -> None:
    """Read the circuit state from the breaker and update the Prometheus gauge."""
    try:
        cb = wrapped.__self__  # circuitbreaker library attaches state to __self__
        if cb.current_state == "closed":
            state = _STATE_CLOSED
        elif cb.current_state == "half-open":
            state = _STATE_HALF_OPEN
        else:
            state = _STATE_OPEN
        circuit_breaker_state.labels(tool=tool, resource_type=resource_type).set(state)
    except AttributeError:
        pass
