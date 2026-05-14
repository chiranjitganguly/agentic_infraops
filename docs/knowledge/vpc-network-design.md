# VPC Network Design Best Practices

## Overview

The platform supports basic VPC provisioning: creating a custom VPC network and one or more subnets within it. Advanced networking features (Shared VPC, VPC peering, Cloud Interconnect) require a platform engineering request.

## When to Create a Custom VPC

Use the `default` VPC for development and testing workloads. Create a custom VPC when:

- You need network isolation between teams or environments
- You require specific subnet CIDR ranges for integration with on-premises networks
- You are building a production environment that must be isolated from dev/staging

## Subnet CIDR Planning

Choose non-overlapping CIDR ranges. Recommended allocations:

| Environment | Suggested CIDR |
|---|---|
| Production | 10.0.0.0/16 |
| Staging | 10.1.0.0/16 |
| Development | 10.2.0.0/16 |

Each subnet should be a /24 or smaller (e.g., `10.0.1.0/24`) within the VPC's range. Avoid using /8 or /16 subnet masks directly — they leave no room for subnet expansion.

## Firewall Rules

The platform provisions VPCs with a default-deny ingress rule. You must explicitly request firewall rules as part of your provisioning request or create them separately. Common rules to request:

- `allow-internal`: allow all TCP/UDP/ICMP between resources in the same VPC
- `allow-ssh-iap`: allow SSH via Identity-Aware Proxy (recommended over public SSH)
- `allow-http-lb`: allow HTTP/HTTPS from Google's load balancer IP ranges

Do not open port 22 (SSH) or port 3389 (RDP) directly to `0.0.0.0/0`. Use IAP tunnelling instead.

## Private Google Access

Enable **Private Google Access** on all subnets. This allows VMs without external IPs to reach Google APIs (Cloud Storage, Pub/Sub, etc.) over Google's internal network without traversing the internet.

All subnets provisioned through this platform have Private Google Access enabled by default.

## Cloud NAT

If VMs in your VPC need outbound internet access (e.g., to pull packages from public registries) but should not have external IPs, request a Cloud NAT gateway as part of your VPC provisioning.

## DNS

All VPCs provisioned through the platform use Google's internal DNS (`169.254.169.254`). Custom DNS servers are not supported through self-service provisioning.

## Best Practice Summary

- Use custom VPCs for production; default VPC is acceptable for dev/test
- Plan CIDR ranges before provisioning — they cannot be changed after creation
- Never expose SSH/RDP directly to the internet; use IAP
- Enable Private Google Access on all subnets
- Request Cloud NAT if outbound internet access is needed
- Label all VPC resources with `team`, `environment`, and `managed-by=infraops-platform`
