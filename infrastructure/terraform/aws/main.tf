# infrastructure/terraform/aws/main.tf
terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# VPC and Networking
resource "aws_vpc" "airsense_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "airsense-vpc"
    Environment = var.environment
  }
}

resource "aws_subnet" "private_subnets" {
  count             = length(var.availability_zones)
  vpc_id            = aws_vpc.airsense_vpc.id
  cidr_block        = "10.0.${count.index + 1}.0/24"
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name        = "airsense-private-subnet-${count.index + 1}"
    Environment = var.environment
  }
}

resource "aws_subnet" "public_subnets" {
  count                   = length(var.availability_zones)
  vpc_id                  = aws_vpc.airsense_vpc.id
  cidr_block              = "10.0.${count.index + 10}.0/24"
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name        = "airsense-public-subnet-${count.index + 1}"
    Environment = var.environment
  }
}

# EKS Cluster
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 19.0"

  cluster_name    = "airsense-eks-${var.environment}"
  cluster_version = "1.27"

  vpc_id                         = aws_vpc.airsense_vpc.id
  subnet_ids                     = aws_subnet.private_subnets[*].id
  cluster_endpoint_public_access = true

  eks_managed_node_groups = {
    main = {
      name = "airsense-nodes"

      instance_types = ["m5.large"]
      capacity_type  = "ON_DEMAND"

      min_size     = 2
      max_size     = 10
      desired_size = 3

      update_config = {
        max_unavailable_percentage = 33
      }

      labels = {
        Environment = var.environment
        Application = "airsense"
      }
    }
  }

  tags = {
    Environment = var.environment
    Application = "airsense"
  }
}

# RDS Database
resource "aws_db_subnet_group" "airsense_db_subnet_group" {
  name       = "airsense-db-subnet-group"
  subnet_ids = aws_subnet.private_subnets[*].id

  tags = {
    Name        = "airsense-db-subnet-group"
    Environment = var.environment
  }
}

resource "aws_db_instance" "airsense_postgres" {
  identifier = "airsense-postgres-${var.environment}"

  engine         = "postgres"
  engine_version = "15.3"
  instance_class = "db.t3.medium"

  allocated_storage     = 100
  max_allocated_storage = 1000
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "airsense"
  username = "airsense"
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.airsense_db_subnet_group.name
  vpc_security_group_ids = [aws_security_group.rds_sg.id]

  backup_retention_period = 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "sun:04:00-sun:05:00"

  skip_final_snapshot = var.environment == "dev"
  deletion_protection = var.environment == "prod"

  performance_insights_enabled = true
  monitoring_interval         = 60

  tags = {
    Name        = "airsense-postgres"
    Environment = var.environment
  }
}

# ElastiCache Redis
resource "aws_elasticache_subnet_group" "airsense_cache_subnet_group" {
  name       = "airsense-cache-subnet-group"
  subnet_ids = aws_subnet.private_subnets[*].id
}

resource "aws_elasticache_replication_group" "airsense_redis" {
  replication_group_id       = "airsense-redis-${var.environment}"
  description                = "Redis cluster for AirSense platform"

  node_type            = "cache.t3.micro"
  port                 = 6379
  parameter_group_name = "default.redis7"

  num_cache_clusters = 2
  
  subnet_group_name  = aws_elasticache_subnet_group.airsense_cache_subnet_group.name
  security_group_ids = [aws_security_group.redis_sg.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  tags = {
    Name        = "airsense-redis"
    Environment = var.environment
  }
}

# S3 Data Lake
resource "aws_s3_bucket" "airsense_data_lake" {
  bucket = "airsense-data-lake-${var.environment}-${random_string.bucket_suffix.result}"

  tags = {
    Name        = "airsense-data-lake"
    Environment = var.environment
  }
}

resource "aws_s3_bucket_versioning" "airsense_data_lake_versioning" {
  bucket = aws_s3_bucket.airsense_data_lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "airsense_data_lake_encryption" {
  bucket = aws_s3_bucket.airsense_data_lake.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# MSK Kafka Cluster
resource "aws_msk_cluster" "airsense_kafka" {
  cluster_name           = "airsense-kafka-${var.environment}"
  kafka_version          = "3.4.0"
  number_of_broker_nodes = 3

  broker_node_group_info {
    instance_type   = "kafka.m5.large"
    client_subnets  = aws_subnet.private_subnets[*].id
    security_groups = [aws_security_group.msk_sg.id]

    storage_info {
      ebs_storage_info {
        volume_size = 100
      }
    }
  }

  encryption_info {
    encryption_at_rest_kms_key_id = aws_kms_key.airsense_key.arn
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  tags = {
    Name        = "airsense-kafka"
    Environment = var.environment
  }
}

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "airsense_api_logs" {
  name              = "/aws/airsense/api"
  retention_in_days = 30

  tags = {
    Environment = var.environment
    Application = "airsense-api"
  }
}

resource "aws_cloudwatch_log_group" "airsense_airflow_logs" {
  name              = "/aws/airsense/airflow"
  retention_in_days = 30

  tags = {
    Environment = var.environment
    Application = "airsense-airflow"
  }
}

# Security Groups
resource "aws_security_group" "rds_sg" {
  name_prefix = "airsense-rds-"
  vpc_id      = aws_vpc.airsense_vpc.id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.airsense_vpc.cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "airsense-rds-sg"
    Environment = var.environment
  }
}

resource "aws_security_group" "redis_sg" {
  name_prefix = "airsense-redis-"
  vpc_id      = aws_vpc.airsense_vpc.id

  ingress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.airsense_vpc.cidr_block]
  }

  tags = {
    Name        = "airsense-redis-sg"
    Environment = var.environment
  }
}

resource "aws_security_group" "msk_sg" {
  name_prefix = "airsense-msk-"
  vpc_id      = aws_vpc.airsense_vpc.id

  ingress {
    from_port   = 9092
    to_port     = 9094
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.airsense_vpc.cidr_block]
  }

  tags = {
    Name        = "airsense-msk-sg"
    Environment = var.environment
  }
}

# KMS Key
resource "aws_kms_key" "airsense_key" {
  description             = "KMS key for AirSense platform encryption"
  deletion_window_in_days = 7

  tags = {
    Name        = "airsense-kms-key"
    Environment = var.environment
  }
}

resource "random_string" "bucket_suffix" {
  length  = 8
  special = false
  upper   = false
}

# Variables
variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-west-2"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "prod"
}

variable "availability_zones" {
  description = "Availability zones"
  type        = list(string)
  default     = ["us-west-2a", "us-west-2b", "us-west-2c"]
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

# Outputs
output "eks_cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = module.eks.cluster_endpoint
}

output "rds_endpoint" {
  description = "RDS instance endpoint"
  value       = aws_db_instance.airsense_postgres.endpoint
}

output "redis_endpoint" {
  description = "Redis cluster endpoint"
  value       = aws_elasticache_replication_group.airsense_redis.primary_endpoint_address
}

output "kafka_bootstrap_servers" {
  description = "MSK cluster bootstrap servers"
  value       = aws_msk_cluster.airsense_kafka.bootstrap_brokers
}