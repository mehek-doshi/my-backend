"""Import every model so Base.metadata (and Alembic) sees all tables."""
from app.db.models.agents import AgentCheckpoint, AgentEvent, AgentRun, DiscoverySession, JobExecution
from app.db.models.identity import Category, TechnologySource, User
from app.db.models.system import (AppSetting, AuditLog, Badge, Certificate, IntegrationState, Notification,
                                  UserBadge)
from app.db.models.topics import SourceArticle, Topic, TopicReview, TopicTestCase
from app.db.models.workflow import Artifact, Assignment, Invitation, ModerationRecord, Volunteer

__all__ = [
    "AgentCheckpoint", "AgentEvent", "AgentRun", "AppSetting", "Artifact", "Assignment", "AuditLog", "Badge",
    "Category", "Certificate", "DiscoverySession", "IntegrationState", "Invitation", "JobExecution",
    "ModerationRecord", "Notification", "SourceArticle", "TechnologySource", "Topic", "TopicReview",
    "TopicTestCase", "User", "UserBadge", "Volunteer",
]
