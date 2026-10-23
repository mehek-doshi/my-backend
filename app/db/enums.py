"""Explicit lifecycle states and other enumerations."""
import enum


class Role(enum.StrEnum):
    EMPLOYEE = "Employee"
    ADMIN = "Admin"
    MODERATOR = "Moderator"  # legacy value kept in the DB check constraint only; nobody is assigned it any more


class TopicStatus(enum.StrEnum):
    DISCOVERED = "discovered"
    ENRICHED = "enriched"
    CLASSIFIED = "classified"
    BLOCKED = "blocked"                      # stopped by a guardrail
    UNVERIFIED = "unverified"                # sources could not be verified
    PENDING_REVIEW = "pending_review"        # verified, waiting for a human
    OPEN_FOR_VOLUNTEERS = "open_for_volunteers"
    IN_PROGRESS = "in_progress"
    REJECTED = "rejected"
    MERGED = "merged"
    ARCHIVED = "archived"


class TopicOrigin(enum.StrEnum):
    AGENT = "agent"
    CUSTOM = "custom"


class Stage(enum.StrEnum):
    STUDY = "Study"
    POC = "POC"
    PRESENTATION = "Presentation"


STAGE_ORDER = [Stage.STUDY, Stage.POC, Stage.PRESENTATION]


class InvitationStatus(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    REVOKED = "revoked"


class VolunteerStatus(enum.StrEnum):
    ACTIVE = "active"
    WAITLISTED = "waitlisted"
    REMOVED = "removed"
    COMPLETED = "completed"


class AssignmentStatus(enum.StrEnum):
    OPEN = "open"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ArtifactStatus(enum.StrEnum):
    SUBMITTED = "submitted"
    SCANNING = "scanning"
    QUARANTINED = "quarantined"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ArtifactType(enum.StrEnum):
    POC = "poc"
    ARCHITECTURE_PATTERN = "architecture_pattern"
    CODEBASE = "codebase"
    DOCUMENT = "document"
    PRESENTATION = "presentation"
    USE_CASE = "use_case"


class RunStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"      # finished, but some sources/items failed
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"      # e.g. the integration is not configured


class DiscoveryTrigger(enum.StrEnum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class SourceKind(enum.StrEnum):
    FEED = "feed"            # RSS 2.0, RSS 1.0 (RDF) or Atom


class EventLevel(enum.StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class NotificationChannel(enum.StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"
    TEAMS = "teams"
    BUDDY = "buddy"


class NotificationStatus(enum.StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class ReviewDecision(enum.StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    MERGED = "merged"
    VERIFIED = "verified"    # manual verification by a reviewer


class ModerationDecision(enum.StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"


class BadgeCriterion(enum.StrEnum):
    VOLUNTEER = "volunteer"
    TESTCASES = "testcases"
    ARTIFACTS = "artifacts"
    PRESENTATIONS = "presentations"
    TOPICS = "topics"
