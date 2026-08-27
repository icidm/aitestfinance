from prometheus_client import Counter, Gauge
from prometheus_fastapi_instrumentator import Instrumentator

# Patch routing to handle FastAPI 0.115+ _IncludedRouter mounts safely
try:
    import prometheus_fastapi_instrumentator.routing as prom_routing

    def _safe_get_route_name(scope, routes, route_name=None):
        # Simplified: return templated path if available else raw path
        raw = scope.get("path", "unknown")
        # Try to find templated route via scope endpoint
        endpoint = scope.get("endpoint")
        if endpoint:
            # attempt to map via route path_format
            for r in routes:
                try:
                    match, child = r.matches(scope)
                    if str(match) == "Match.FULL" or match == 2:  # 2 is FULL enum value
                        p = getattr(r, "path", None) or getattr(r, "path_format", None) or raw
                        return str(p)
                except Exception:
                    continue
        return raw

    prom_routing._get_route_name = _safe_get_route_name

    # Also patch get_route_name(request) helper
    def _safe_get_route_name_req(request):
        try:
            return (
                request.scope.get("endpoint").__name__
                if request.scope.get("endpoint")
                else request.url.path
            )
        except Exception:
            return request.url.path

    # Instrumentator middleware uses routing.get_route_name(request) in newer versions
    if hasattr(prom_routing, "get_route_name"):
        orig = prom_routing.get_route_name
        try:
            # If get_route_name expects request object, wrap
            import inspect

            sig = inspect.signature(orig)
            if "request" in sig.parameters:
                prom_routing.get_route_name = _safe_get_route_name_req
        except Exception:
            pass
except Exception:
    pass

# Custom counters
incident_created_total = Counter("incident_created_total", "Total incidents created", ["severity"])
incident_resolved_total = Counter(
    "incident_resolved_total", "Total incidents resolved", ["severity"]
)
sse_connections_active = Gauge("sse_connections_active", "Active SSE connections")
sse_events_total = Counter("sse_events_total", "Total SSE events sent")

instrumentator = Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    should_instrument_requests_inprogress=True,
)


def setup_instrumentator(app):
    instrumentator.instrument(app).expose(
        app, endpoint="/metrics", include_in_schema=False, tags=["metrics"]
    )
    return instrumentator
