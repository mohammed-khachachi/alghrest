terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
  }
  backend "s3" {
    bucket         = "alghrest-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "alghrest-terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "ALGHREST"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# 1. VPC Configuration
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.1.2"

  name = "alghrest-vpc-${var.environment}"
  cidr = var.vpc_cidr

  azs             = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = true
}

# 2. Amazon EKS (Kubernetes Cluster)
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 19.0"

  cluster_name    = "alghrest-cluster-${var.environment}"
  cluster_version = "1.28"

  vpc_id                   = module.vpc.vpc_id
  subnet_ids               = module.vpc.private_subnets
  control_plane_subnet_ids = module.vpc.private_subnets

  eks_managed_node_groups = {
    general = {
      desired_size = 3
      min_size     = 3
      max_size     = 6

      instance_types = ["t3.xlarge"] # Need good RAM for Kafka/ML
      capacity_type  = "ON_DEMAND"
    }
    ml_nodes = {
      desired_size = 1
      min_size     = 1
      max_size     = 2
      instance_types = ["g4dn.xlarge"] # GPU node for ML Inference
      capacity_type  = "SPOT"
    }
  }
}

# 3. Redis (ElastiCache)
resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "alghrest-redis-${var.environment}"
  engine               = "redis"
  node_type            = "cache.t3.medium"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379
  security_group_ids   = [aws_security_group.redis_sg.id]
  subnet_group_name    = aws_elasticache_subnet_group.redis_subnet.name
}

resource "aws_elasticache_subnet_group" "redis_subnet" {
  name       = "alghrest-redis-subnet"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "redis_sg" {
  name_prefix = "alghrest-redis-sg-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
}

# 4. Amazon MSK (Authenticated SASL/SCRAM-SHA-512 + TLS + Default-Deny ACLs)
resource "aws_kms_key" "kafka_kms" {
  description             = "KMS key for ALGHREST MSK storage and SASL/SCRAM Secrets Manager credentials"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_security_group" "kafka_sg" {
  name_prefix = "alghrest-kafka-sg-"
  vpc_id      = module.vpc.vpc_id

  # Port 9096: SASL/SCRAM over TLS only (plaintext 9092 disabled)
  ingress {
    from_port   = 9096
    to_port     = 9096
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
    description = "Kafka SASL/SCRAM TLS from VPC worker nodes"
  }
}

resource "aws_msk_configuration" "kafka_config" {
  name              = "alghrest-kafka-config-${var.environment}"
  kafka_versions    = [var.kafka_version]
  server_properties = <<PROPERTIES
auto.create.topics.enable=false
delete.topic.enable=true
default.replication.factor=3
min.insync.replicas=2
unclean.leader.election.enable=false
offsets.topic.replication.factor=3
transaction.state.log.replication.factor=3
transaction.state.log.min.isr=2
allow.everyone.if.no.acl.found=false
compression.type=lz4
log.retention.hours=168
PROPERTIES
}

resource "aws_secretsmanager_secret" "kafka_scram" {
  for_each   = var.kafka_scram_principals
  name       = "AmazonMSK_alghrest_${var.environment}_${each.key}"
  kms_key_id = aws_kms_key.kafka_kms.arn
}

resource "aws_msk_cluster" "kafka" {
  cluster_name           = "alghrest-kafka-${var.environment}"
  kafka_version          = var.kafka_version
  number_of_broker_nodes = 3

  broker_node_group_info {
    instance_type   = var.kafka_instance_type
    client_subnets  = module.vpc.private_subnets
    security_groups = [aws_security_group.kafka_sg.id]

    storage_info {
      ebs_storage_info {
        volume_size = 500
      }
    }
  }

  client_authentication {
    unauthenticated = false
    sasl {
      scram = true
      iam   = false
    }
  }

  encryption_info {
    encryption_at_rest_kms_key_arn = aws_kms_key.kafka_kms.arn
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.kafka_config.arn
    revision = aws_msk_configuration.kafka_config.latest_revision
  }
}

resource "aws_msk_scram_secret_association" "kafka_scram_assoc" {
  cluster_arn     = aws_msk_cluster.kafka.arn
  secret_arn_list = [for secret in aws_secretsmanager_secret.kafka_scram : secret.arn]
}
