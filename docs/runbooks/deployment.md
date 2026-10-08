# ALGHREST Infrastructure Deployment Guide

Run repository commands from the repository root, not from `docs/runbooks/`.

For manual research or local paper use, first select an
[explicit operating mode](../maintenance/runtime-efficiency.md). The full stack
below is not required for those workflows. Preview with
`python -m scripts.runtime research plan` or `python -m scripts.runtime paper plan`.

## Select the operating profile

For Earn2Trade manual research, set `OPERATING_PROFILE=earn2trade_tcp25` before
launching `python -m api.advisor`, or use the isolated
`docker-compose.advisor.yml`, which fixes that profile and omits the trading
`.env`. Preview it with `python -m scripts.runtime research plan`. It runs on
loopback port 8011 and has no broker order path.

`ENVIRONMENT=live` does not grant execution to the advisory profile. Legacy
agents, order producers, venues, recovery processing, the trading API, and
paper/full startup are denied. Plan/status commands remain available.
`OPERATING_PROFILE=general` retains the existing non-Earn2Trade workflow and
its separate environment/readiness gates. Run the two profiles in separate
processes; select the profile before startup. Existing running services are not
reconfigured by editing environment variables.

## Prerequisites Checklist

### 1. Environment Setup
```bash
# Ensure .env file is properly configured
cp .env.example .env  # if not already done
# Edit .env with your actual API keys and settings
```

### 2. System Requirements
- Docker Engine 20.10+ 
- Docker Compose v2.0+
- At least 8GB RAM available
- 20GB+ disk space for data volumes

## Deployment Steps

### 1. Start the Infrastructure Stack
```bash
# Navigate to project directory
cd /path/to/alghrest-main

# Pull latest images and start services
docker compose pull
docker compose up -d
```

### 2. Expected Output
```
[+] Running 37/37
✔ Network alghrest_alghrest-network          Created
✔ Volume "alghrest_timescale-data"           Created
✔ Volume "alghrest_kafka-data-1"             Created
✔ Volume "alghrest_redis-data"               Created
✔ Container alghrest-zookeeper               Started
✔ Container alghrest-redis                   Started
✔ Container alghrest-timescaledb             Started
✔ Container alghrest-kafka-1                 Started
✔ Container alghrest-kafka-2                 Started
✔ Container alghrest-kafka-3                 Started
✔ Container alghrest-kafka-init              Started
✔ Container alghrest-schema-registry         Started
✔ Container alghrest-kafka-ui                Started
✔ Container alghrest-api                     Started
✔ Container alghrest-agent-cio               Started
... (20 agent containers)
✔ Container alghrest-dashboard               Started
✔ Container alghrest-grafana                 Started
✔ Container alghrest-prometheus              Started
```

### 3. Verify Deployment

#### Check Service Status
```bash
# View all services
docker compose ps

# Should show 37 services with status "running" or "exited" (for kafka-init)
```

#### Verify Kafka Topics Creation
```bash
# Check kafka initialization logs
docker compose logs kafka-init

# Should end with: "All 18 Kafka topics initialized successfully."
```

#### Check Core Services Health
```bash
# Redis
docker compose exec redis redis-cli ping
# Expected: PONG

# TimescaleDB
docker compose exec timescaledb pg_isready -U alghrest
# Expected: accepting connections

# Kafka
docker compose exec kafka-1 kafka-topics --bootstrap-server localhost:29092 --list
# Expected: List of 18 topics
```

### 4. Access Web Interfaces

#### Kafka UI (Development)
- **URL:** http://localhost:8080
- **Purpose:** Monitor Kafka topics, messages, consumers

#### Grafana (Monitoring)
- **URL:** http://localhost:3000
- **Login:** admin / alghrest_grafana_2024
- **Purpose:** System metrics and dashboards

#### API Documentation
- **URL:** http://localhost:8000/docs
- **Purpose:** FastAPI Swagger documentation

#### Dashboard (Frontend)
- **URL:** http://localhost:5173
- **Purpose:** Trading dashboard interface

### 5. Verify Agent Services

#### Check Agent Health
```bash
# View agent logs
docker compose logs agent-cio
docker compose logs agent-price-publisher

# Check Prometheus metrics
curl http://localhost:9201/metrics  # CIO Agent (9200 + agent_id)
curl http://localhost:9204/metrics  # Price Publisher
```

#### Monitor Agent Communication
```bash
# Watch Kafka topics for agent messages
docker compose exec kafka-ui kafka-console-consumer \
  --bootstrap-server kafka-1:29092 \
  --topic prices.realtime \
  --from-beginning
```

## Troubleshooting

### Common Issues

#### 1. Port Conflicts
```bash
# Check which ports are in use
netstat -tulpn | grep :5432  # TimescaleDB
netstat -tulpn | grep :6379  # Redis
netstat -tulpn | grep :9092  # Kafka

# Solution: Stop conflicting services or change ports in docker-compose.yml
```

#### 2. Insufficient Resources
```bash
# Check system resources
docker stats

# Solution: Increase Docker memory limit or reduce service resource limits
```

#### 3. Failed Health Checks
```bash
# Check specific service health
docker compose ps
docker compose logs <service-name>

# Common fixes:
# - Wait longer for services to initialize
# - Check .env configuration
# - Verify volume permissions
```

#### 4. Kafka Topics Not Created
```bash
# Check kafka-init container logs
docker compose logs kafka-init

# If failed, restart kafka-init
docker compose restart kafka-init
```

#### 5. TimescaleDB Connection Issues
```bash
# Verify database initialization
docker compose logs timescaledb

# Check database is accessible
docker compose exec timescaledb psql -U alghrest -d alghrest -c "\l"
```

### Performance Tuning

#### For Development
```bash
# Use fewer replicas for faster startup
KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 docker compose up -d
```

#### For Production
- Increase memory limits in docker-compose.yml
- Use external volumes for persistent data
- Enable monitoring and alerting
- Configure backup procedures

## Shutdown

### Graceful Shutdown
```bash
# Stop all services gracefully
docker compose down

# Stop and remove volumes (WARNING: data loss)
docker compose down -v
```

### Cleanup
```bash
# Remove unused Docker resources
docker system prune -a

# Remove specific volumes if needed
docker volume rm alghrest_timescale-data
```

## Next Steps After Successful Deployment

1. **Verify Data Flow:** Check agent logs for message processing
2. **Test API Endpoints:** Use FastAPI docs to test trading endpoints  
3. **Monitor Metrics:** Set up Grafana dashboards
4. **Load Test Data:** Import sample market data for testing
5. **Configure Alerts:** Set up monitoring and alerting rules

## Support

### Log Collection for Issues
```bash
# Collect all logs
docker compose logs > alghrest_logs.txt

# Service-specific logs
docker compose logs agent-cio > cio_logs.txt
docker compose logs timescaledb > db_logs.txt
```

### Health Check Script
```bash
#!/bin/bash
# Quick health check script
echo "=== ALGHREST Health Check ==="
echo "Services running: $(docker compose ps --services --filter status=running | wc -l)/37"
echo "Kafka topics: $(docker compose exec kafka-1 kafka-topics --bootstrap-server localhost:29092 --list 2>/dev/null | wc -l)"
echo "Redis status: $(docker compose exec redis redis-cli ping 2>/dev/null || echo 'FAILED')"
echo "Database status: $(docker compose exec timescaledb pg_isready -U alghrest 2>/dev/null || echo 'FAILED')"
```
