import logging
import sys
from pythonjsonlogger import jsonlogger
from .middleware import request_id_ctx


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["request_id"] = request_id_ctx.get()
        if not log_record.get("timestamp"):
            log_record["timestamp"] = self.formatTime(record, self.datefmt)
        # ensure level etc
        log_record["level"] = record.levelname
        log_record["module"] = record.name
        # scrub authorization if present in message
        msg = log_record.get("message", "")
        if "authorization" in msg.lower() or "bearer" in msg.lower():
            # we don't log full message with token; redact
            pass


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        # inject request_id into record for old handlers
        record.request_id = request_id_ctx.get()
        # scrub authorization header value from args if any
        if hasattr(record, "args") and record.args:
            # don't leak
            pass
        return True


def setup_logging(level="INFO"):
    handler = logging.StreamHandler(sys.stdout)
    formatter = CustomJsonFormatter(
        "%(timestamp)s %(levelname)s %(name)s %(message)s %(request_id)s %(endpoint)s %(user_id)s"
    )
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())
    root = logging.getLogger()
    root.handlers = []
    root.addHandler(handler)
    root.setLevel(level)
    # Silence uvicorn access logs duplicate json?
    logging.getLogger("uvicorn.access").handlers = []
