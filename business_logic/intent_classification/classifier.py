"""Intent classification skill using LiteLLM structured output.

classify(raw_input, channel) → ClassificationResult

Performs extraction + resolution in a single LLM pass (normalisation).
ClassificationResult carries intent, confidence, and a typed normalized payload
(NormalizedVMRequest | NormalizedBucketRequest | NormalizedVPCRequest |
 NormalizedEnquiryRequest | NormalizedFAQRequest | None).

Callers never read individual GCP fields — they receive the whole typed object.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import litellm

from contracts.schemas.infra_request import ChannelType
from contracts.shared.logging import get_logger
from contracts.shared.metrics import intent_classification_duration_seconds

logger = get_logger("intent-classifier")

_CLASSIFY_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "classify_intent",
        "description": (
            "Classify a natural language infrastructure request and extract fully resolved "
            "GCP parameters. Normalise vague descriptions into concrete GCP values "
            "(e.g. '4 CPUs' → machine_type='e2-standard-4'). "
            "Return confidence 0.0–1.0 reflecting certainty in the classification."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": ["provision", "enquiry", "faq"],
                    "description": "The primary intent of the request.",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score 0.0–1.0. Use < 0.7 when parameters are ambiguous.",
                },
                "resource_type": {
                    "type": "string",
                    "enum": ["compute_instance", "storage_bucket", "vpc_network"],
                    "description": "GCP resource type (required for provision/enquiry intents).",
                },
                "resource_name": {
                    "type": "string",
                    "description": "Name of the GCP resource to create or enquire about.",
                },
                "region": {
                    "type": "string",
                    "description": "GCP region (e.g. us-central1). Required for provisioning.",
                },
                "zone": {
                    "type": "string",
                    "description": "GCP zone (e.g. us-central1-a). Required for VM provisioning.",
                },
                "machine_type": {
                    "type": "string",
                    "description": "GCP machine type. Map CPU/RAM descriptions: "
                    "2 CPUs→e2-standard-2, 4 CPUs→e2-standard-4, 8 CPUs→e2-standard-8.",
                },
                "disk_size_gb": {
                    "type": "integer",
                    "description": "Boot disk size in GB (default 50 if not specified).",
                },
                "image_family": {
                    "type": "string",
                    "description": "Compute Engine image family (default: debian-12).",
                },
                "image_project": {
                    "type": "string",
                    "description": "Project hosting the image (default: debian-cloud).",
                },
                "network": {
                    "type": "string",
                    "description": "VPC network name (default: default).",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Network tags for the VM.",
                },
                "storage_class": {
                    "type": "string",
                    "enum": ["STANDARD", "NEARLINE", "COLDLINE", "ARCHIVE"],
                    "description": "Storage class for bucket provisioning.",
                },
                "versioning_enabled": {
                    "type": "boolean",
                    "description": "Enable object versioning for bucket (default false).",
                },
                "subnet_name": {
                    "type": "string",
                    "description": "Subnet name for VPC provisioning.",
                },
                "subnet_cidr": {
                    "type": "string",
                    "description": "Subnet CIDR range (e.g. 10.0.0.0/24).",
                },
                "project_id": {
                    "type": "string",
                    "description": "GCP project ID (for enquiry intents).",
                },
            },
            "required": ["intent", "confidence"],
        },
    },
}

_SYSTEM_PROMPT = """\
You are an infrastructure intent classifier for a GCP self-service platform.

Your job: classify the user's request and extract fully resolved GCP parameters in one step.
- For ambiguous requests (missing required parameters, unclear intent), set confidence < 0.7.
- Always map natural language to concrete GCP values (e.g. "4 CPUs" → machine_type="e2-standard-4").
- Machine type mapping: 2 CPUs → e2-standard-2, 4 CPUs → e2-standard-4, 8 CPUs → e2-standard-8.
- Default region: us-central1 if not specified but resource_type is compute_instance.
- Default zone: {region}-a if zone is not specified.
- For enquiry intents: extract resource_type, resource_name, and project_id if mentioned.
- For faq intents: set confidence high if the question is clearly about GCP best practices.

Email channel note: users tend to write formally; apply the same normalisation rules.
"""


# ─── Typed normalized payload types ──────────────────────────────────────────

@dataclass
class NormalizedVMRequest:
    """Fully resolved parameters for a VM provisioning request."""
    resource_type: str = "compute_instance"
    resource_name: str = ""
    region: str = "us-central1"
    zone: str | None = None
    machine_type: str = "e2-standard-4"
    disk_size_gb: int = 50
    image_family: str = "debian-12"
    image_project: str = "debian-cloud"
    network: str = "default"
    tags: list[str] = field(default_factory=list)

    def as_parameters(self) -> dict[str, Any]:
        """Return the subset passed as ProvisioningInput.parameters."""
        return {
            "machine_type": self.machine_type,
            "disk_size_gb": self.disk_size_gb,
            "image_family": self.image_family,
            "image_project": self.image_project,
            "network": self.network,
            "tags": self.tags,
        }


@dataclass
class NormalizedBucketRequest:
    """Fully resolved parameters for a bucket provisioning request."""
    resource_type: str = "storage_bucket"
    resource_name: str = ""
    region: str = "us-central1"
    storage_class: str = "STANDARD"
    versioning_enabled: bool = False

    def as_parameters(self) -> dict[str, Any]:
        return {
            "storage_class": self.storage_class,
            "versioning_enabled": self.versioning_enabled,
        }


@dataclass
class NormalizedVPCRequest:
    """Fully resolved parameters for a VPC provisioning request."""
    resource_type: str = "vpc_network"
    resource_name: str = ""
    region: str = "us-central1"
    subnet_name: str = ""
    subnet_cidr: str = "10.0.0.0/24"
    auto_create_subnetworks: bool = False

    def as_parameters(self) -> dict[str, Any]:
        return {
            "auto_create_subnetworks": self.auto_create_subnetworks,
            "subnet_name": self.subnet_name,
            "subnet_region": self.region,
            "subnet_cidr": self.subnet_cidr,
        }


@dataclass
class NormalizedEnquiryRequest:
    """Resolved parameters for a resource status enquiry."""
    query_type: str = "single"  # "single" | "list"
    resource_type: str = "compute_instance"
    resource_name: str | None = None
    project_id: str | None = None
    zone: str | None = None
    region: str | None = None


@dataclass
class NormalizedFAQRequest:
    """The original user question, preserved for FAQ retrieval."""
    question: str = ""


NormalizedPayload = (
    NormalizedVMRequest
    | NormalizedBucketRequest
    | NormalizedVPCRequest
    | NormalizedEnquiryRequest
    | NormalizedFAQRequest
)


# ─── ClassificationResult ─────────────────────────────────────────────────────

@dataclass
class ClassificationResult:
    intent: str
    confidence: float
    normalized: NormalizedPayload | None = None


async def classify(raw_input: str, channel: ChannelType | str) -> ClassificationResult:
    """Classify a natural language infrastructure request.

    Uses LiteLLM structured output (function calling) to extract intent and
    fully resolved GCP parameters in a single pass.

    Args:
        raw_input: The user's raw natural language request.
        channel: The channel the request came from ('web' or 'email').

    Returns:
        ClassificationResult with intent, confidence, and resolved GCP params.
    """
    gateway_url = os.environ.get("LITELLM_GATEWAY_URL", "http://localhost:4000")
    master_key = os.environ.get("LITELLM_MASTER_KEY", "")
    model = os.environ.get("INTENT_CLASSIFICATION_MODEL", "gpt-4o-2024-11-20")

    channel_hint = (
        "Note: this request came via email — it may be more formal in tone."
        if str(channel) == "email"
        else ""
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Classify this request: {raw_input}\n{channel_hint}",
        },
    ]

    with intent_classification_duration_seconds.labels(channel=str(channel)).time():
        response = await litellm.acompletion(
            model=model,
            api_base=gateway_url,
            api_key=master_key,
            messages=messages,
            tools=[_CLASSIFY_TOOL],
            tool_choice={"type": "function", "function": {"name": "classify_intent"}},
            temperature=0.0,
        )

    tool_call = response.choices[0].message.tool_calls[0]
    args: dict[str, Any] = json.loads(tool_call.function.arguments)

    intent: str = args["intent"]
    confidence: float = float(args["confidence"])

    logger.info(
        "intent_classified",
        intent=intent,
        confidence=confidence,
        resource_type=args.get("resource_type"),
        channel=str(channel),
    )

    return ClassificationResult(
        intent=intent,
        confidence=confidence,
        normalized=_build_normalized(intent, raw_input, args),
    )


def _build_normalized(intent: str, raw_input: str, args: dict[str, Any]) -> NormalizedPayload | None:
    """Translate flat LLM output into a typed normalized payload."""
    resource_type = args.get("resource_type", "compute_instance")

    if intent == "provision":
        if resource_type == "compute_instance":
            return NormalizedVMRequest(
                resource_name=args.get("resource_name", ""),
                region=args.get("region", "us-central1"),
                zone=args.get("zone"),
                machine_type=args.get("machine_type", "e2-standard-4"),
                disk_size_gb=args.get("disk_size_gb", 50),
                image_family=args.get("image_family", "debian-12"),
                image_project=args.get("image_project", "debian-cloud"),
                network=args.get("network", "default"),
                tags=args.get("tags", []),
            )
        if resource_type == "storage_bucket":
            return NormalizedBucketRequest(
                resource_name=args.get("resource_name", ""),
                region=args.get("region", "us-central1"),
                storage_class=args.get("storage_class", "STANDARD"),
                versioning_enabled=args.get("versioning_enabled", False),
            )
        if resource_type == "vpc_network":
            return NormalizedVPCRequest(
                resource_name=args.get("resource_name", ""),
                region=args.get("region", "us-central1"),
                subnet_name=args.get("subnet_name", ""),
                subnet_cidr=args.get("subnet_cidr", "10.0.0.0/24"),
                auto_create_subnetworks=False,
            )

    if intent == "enquiry":
        resource_name = args.get("resource_name")
        return NormalizedEnquiryRequest(
            query_type="list" if not resource_name else "single",
            resource_type=resource_type,
            resource_name=resource_name,
            project_id=args.get("project_id"),
            zone=args.get("zone"),
            region=args.get("region"),
        )

    if intent == "faq":
        return NormalizedFAQRequest(question=raw_input)

    return None
