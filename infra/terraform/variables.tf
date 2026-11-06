variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (e.g., dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "kafka_version" {
  description = "Apache Kafka version for Amazon MSK"
  type        = string
  default     = "3.6.0"
}

variable "kafka_instance_type" {
  description = "Broker instance type for Amazon MSK"
  type        = string
  default     = "kafka.m5.large"
}

variable "kafka_scram_principals" {
  description = "Worker role principals provisioned in AWS Secrets Manager for MSK SASL/SCRAM-SHA-512"
  type        = set(string)
  default = [
    "alghrest",
    "tier1_executive",
    "tier2_intelligence",
    "tier3_quant",
    "tier4_strategy",
    "tier5_router",
    "tier5_executor",
    "tier7_monitoring",
    "advisory_reader",
  ]
}
