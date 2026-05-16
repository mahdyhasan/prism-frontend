# Import all models here so Alembic autogenerate can detect them.
from prism.db.models.tenant import Tenant
from prism.db.models.user import User
from prism.db.models.property import Property, PropertyMember
from prism.db.models.llm_config import PropertyLLMConfig
from prism.db.models.ga4 import (
    GA4ChannelsDaily,
    GA4DailyMetrics,
    GA4DevicesDaily,
    GA4EventsDaily,
    GA4GeoDaily,
    GA4HourlyMetrics,
    GA4LandingPageDeviceDaily,
    GA4LandingPagesDaily,
    GA4TrafficSourcesDaily,
    GA4UserTypeDaily,
)
from prism.db.models.gsc import (
    GSCAppearanceDaily,
    GSCPagesDaily,
    GSCQueriesDaily,
    GSCQueryPageDaily,
    GSCSearchTypeDaily,
)
from prism.db.models.sync import SyncJob, AuditLog
from prism.db.models.insight import Insight, ClaudeCallLog
from prism.db.models.chat import ChatSession, ChatMessage, ChatMemory, PinnedQuestion, PinnedQuestionRun
from prism.db.models.brief import DailyBrief
from prism.db.models.cross_source import XSPageDaily
from prism.db.models.clarity import ClarityPageDaily
from prism.db.models.cwv import CWVOriginAudit, CWVPageAudit, PropertySettings
from prism.db.models.actions import ActionExecution

__all__ = [
    "Tenant",
    "User",
    "Property",
    "PropertyMember",
    "GA4DailyMetrics",
    "GA4LandingPagesDaily",
    "GA4TrafficSourcesDaily",
    "GA4DevicesDaily",
    "GA4GeoDaily",
    "GA4EventsDaily",
    "GA4ChannelsDaily",
    "GA4HourlyMetrics",
    "GA4UserTypeDaily",
    "GA4LandingPageDeviceDaily",
    "GSCQueriesDaily",
    "GSCPagesDaily",
    "GSCQueryPageDaily",
    "GSCAppearanceDaily",
    "GSCSearchTypeDaily",
    "SyncJob",
    "AuditLog",
    "Insight",
    "ClaudeCallLog",
    "ChatSession",
    "ChatMessage",
    "ChatMemory",
    "PinnedQuestion",
    "PinnedQuestionRun",
    "DailyBrief",
    "XSPageDaily",
    "PropertyLLMConfig",
    "ClarityPageDaily",
    "PropertySettings",
    "CWVPageAudit",
    "CWVOriginAudit",
    "ActionExecution",
]
