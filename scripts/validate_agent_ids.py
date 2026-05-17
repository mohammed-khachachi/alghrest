#!/usr/bin/env python3
"""
ALGHREST — Agent ID Validation Script
Validates that Agent IDs in code match ports/IPs in docker-compose.yml
and checks for consistency across the entire system.
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

def extract_agent_ids_from_code() -> Dict[str, int]:
    """Extract AGENT_ID assignments from all agent files."""
    agent_ids = {}
    agents_dir = Path("agents")

    for agent_file in agents_dir.rglob("*.py"):
        if agent_file.name == "__init__.py" or agent_file.name == "base_agent.py":
            continue

        try:
            content = agent_file.read_text()
            # Match AGENT_ID = <number>
            match = re.search(r'AGENT_ID\s*=\s*(\d+)', content)
            if match:
                agent_id = int(match.group(1))
                agent_ids[agent_file.stem] = agent_id
        except Exception as e:
            print(f"Warning: Could not read {agent_file}: {e}")

    return agent_ids

def extract_docker_ports_and_ips() -> Dict[str, Tuple[int, str]]:
    """Extract port mappings and IP addresses from docker-compose.yml."""
    docker_compose = Path("docker-compose.yml")
    if not docker_compose.exists():
        print("Error: docker-compose.yml not found")
        return {}

    content = docker_compose.read_text()
    services = {}

    # Split by service definitions
    service_sections = re.split(r'\n  (\w+(?:-\w+)*):', content)[1:]  # Remove empty first element

    for i in range(0, len(service_sections), 2):
        service_name = service_sections[i]
        service_content = service_sections[i + 1] if i + 1 < len(service_sections) else ""

        # Skip non-agent services
        if not service_name.startswith('agent-'):
            continue

        # Extract port
        port_match = re.search(r'ports:\s*\n\s*-\s*"(\d+):\d+', service_content)
        # Extract IP
        ip_match = re.search(r'ipv4_address:\s*(172\.20\.\d+\.\d+)', service_content)

        if port_match and ip_match:
            port = int(port_match.group(1))
            ip = ip_match.group(1)

            # Convert service name to agent name (remove "agent-" prefix)
            agent_name = service_name.replace("agent-", "").replace("-", "_")
            services[agent_name] = (port, ip)

    return services

def validate_agent_ids():
    """Main validation function."""
    print("🔍 ALGHREST Agent ID Validation")
    print("=" * 50)

    # Extract data
    agent_ids = extract_agent_ids_from_code()
    docker_services = extract_docker_ports_and_ips()

    print(f"\n📁 Found {len(agent_ids)} agents in code")
    print(f"🐳 Found {len(docker_services)} agent services in docker-compose.yml")

    # Check for consistency
    errors = []
    warnings = []

    for agent_name, agent_id in agent_ids.items():
        expected_port = 9200 + agent_id
        expected_ip_suffix = f".{agent_id}"

        if agent_name in docker_services:
            actual_port, actual_ip = docker_services[agent_name]

            # Check port consistency
            if actual_port != expected_port:
                errors.append(f"❌ {agent_name}: Port mismatch - Code ID {agent_id} expects port {expected_port}, but docker-compose has {actual_port}")

            # Check IP consistency (optional, just warning)
            if not actual_ip.endswith(expected_ip_suffix):
                warnings.append(f"⚠️ {agent_name}: IP doesn't match Agent ID - {actual_ip} doesn't end with {expected_ip_suffix}")

        else:
            warnings.append(f"⚠️ {agent_name}: Agent ID {agent_id} found in code but no docker-compose service")

    # Check for services without corresponding agents
    for service_name, (port, ip) in docker_services.items():
        if service_name not in agent_ids:
            warnings.append(f"⚠️ {service_name}: Docker service found but no corresponding agent file")

    # Print results
    print("\n✅ VALIDATION RESULTS")
    print("=" * 30)

    if not errors and not warnings:
        print("🎉 All Agent IDs are consistent!")
        return True

    if errors:
        print(f"\n🚨 {len(errors)} ERRORS found:")
        for error in errors:
            print(f"  {error}")

    if warnings:
        print(f"\n⚠️ {len(warnings)} WARNINGS found:")
        for warning in warnings:
            print(f"  {warning}")

    # Print summary table
    print("\n📊 AGENT ID SUMMARY")
    print("=" * 80)
    print(f"{'Agent Name':<25} {'Code ID':<8} {'Expected Port':<13} {'Docker Port':<12} {'Docker IP':<15} {'Status'}")
    print("-" * 80)

    for agent_name, agent_id in sorted(agent_ids.items()):
        expected_port = 9200 + agent_id

        if agent_name in docker_services:
            docker_port, docker_ip = docker_services[agent_name]
            status = "✅ OK" if docker_port == expected_port else "❌ ERROR"
        else:
            docker_port = "N/A"
            docker_ip = "N/A"
            status = "⚠️ MISSING"

        print(f"{agent_name:<25} {agent_id:<8} {expected_port:<13} {docker_port:<12} {docker_ip:<15} {status}")

    return len(errors) == 0

if __name__ == "__main__":
    success = validate_agent_ids()
    sys.exit(0 if success else 1)