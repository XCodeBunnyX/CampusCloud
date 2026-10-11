"""
cloud_controller package init.
Exposes the Flask Blueprint and the init_db helper.
"""

from cloud_controller.routes import bp
from cloud_controller.services import init_db

__all__ = ["bp", "init_db"]
