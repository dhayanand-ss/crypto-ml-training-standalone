# Kafka Quick Start Guide

## ✅ Your Kafka Cluster is Running!

All services have been successfully started:
- ✅ **Zookeeper** (port 2181) - Coordination service
- ✅ **Kafka Broker** (port 9092) - Message broker
- ✅ **Schema Registry** (port 8081) - Schema management
- ✅ **Kafka REST API** (port 8082) - HTTP interface
- ✅ **Control Center** (port 9021) - Web UI

---

## 🌐 Access the Web Interfaces

### 1. Control Center (Main Kafka UI)
**URL**: http://localhost:9021

**What you can do:**
- View all Kafka topics
- Browse messages in topics
- Monitor consumer groups
- View cluster health and metrics
- Create and manage topics
- View message schemas

**First time setup:**
- The UI may take 1-2 minutes to fully initialize
- You'll see a dashboard with cluster overview

### 2. Kafka REST API
**URL**: http://localhost:8082

**What you can do:**
- Interact with Kafka via HTTP
- View API documentation at: http://localhost:8082/docs
- Send/receive messages using REST calls

### 3. Schema Registry
**URL**: http://localhost:8081

**What you can do:**
- View registered schemas
- Manage schema versions
- Check schema compatibility

---

## 🔧 Common Operations

### Check Kafka Status
```powershell
docker ps --filter "name=kafka|zookeeper|schema-registry|kafka-rest|control-center"
```

### List Topics
```powershell
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --list
```

### Create a Topic
```powershell
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --create --topic test-topic --partitions 1 --replication-factor 1
```

### Produce a Test Message
```powershell
docker exec -it kafka kafka-console-producer --bootstrap-server localhost:9092 --topic test-topic
# Then type your message and press Enter
```

### Consume Messages
```powershell
docker exec -it kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic test-topic --from-beginning
```

### View Topic Details
```powershell
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --describe --topic test-topic
```

---

## 🚀 Next Steps for Your Project

### 1. Start Your Producer
Your producer (`utils/producer_consumer/producer.py`) will:
- Fetch cryptocurrency data from Binance API
- Publish to Kafka topics (one topic per symbol, e.g., `BTCUSDT`)
- Connect to: `localhost:9092`

**Set environment variable:**
```powershell
$env:KAFKA_HOST = "localhost"
```

### 2. Start Your Consumer
Your consumer (`utils/producer_consumer/consumer.py`) will:
- Subscribe to cryptocurrency topics
- Process data and call ML models
- Connect to: `localhost:9092`

**Set environment variable:**
```powershell
$env:KAFKA_HOST = "localhost"
```

### 3. Monitor in Control Center
- Open http://localhost:9021
- Navigate to **Topics** to see your cryptocurrency topics
- View **Consumers** to monitor consumer groups
- Check **Messages** to see real-time data flow

---

## 📝 Configuration for Your Code

### Producer Configuration
```python
KAFKA_BROKER = "localhost:9092"  # For local development
# Or: KAFKA_BROKER = f"{os.environ['KAFKA_HOST']}:9092"  # For Kubernetes
```

### Consumer Configuration
```python
KAFKA_BROKER = "localhost:9092"  # For local development
```

### Topics
- Topics are auto-created when first message is published
- Topic naming: One topic per cryptocurrency symbol (e.g., `BTCUSDT`, `ETHUSDT`)

---

## 🛠️ Troubleshooting

### Services Not Starting
```powershell
# Check logs
docker logs zookeeper
docker logs kafka
docker logs schema-registry
docker logs control-center
```

### Port Conflicts
If ports are already in use:
- Edit `k8-setup/kafka.yml`
- Change port mappings (e.g., `"9093:9092"` instead of `"9092:9092"`)

### Control Center Not Loading
- Wait 1-2 minutes for initialization
- Check logs: `docker logs control-center`
- Ensure all dependencies (Kafka, Schema Registry) are running

### Reset Everything
```powershell
cd k8-setup
docker-compose -f kafka.yml down -v  # -v removes volumes
docker-compose -f kafka.yml up -d
```

---

## 📚 Additional Resources

- **Kafka Documentation**: See `KAFKA_IMPLEMENTATION.md` in project root
- **Control Center Guide**: https://docs.confluent.io/platform/current/control-center/index.html
- **Kafka REST API Docs**: http://localhost:8082/docs

---

## 🎯 Quick Test

Test that everything works:

1. **Create a test topic:**
   ```powershell
   docker exec kafka kafka-topics --bootstrap-server localhost:9092 --create --topic test --partitions 1 --replication-factor 1
   ```

2. **Send a message:**
   ```powershell
   echo "Hello Kafka" | docker exec -i kafka kafka-console-producer --bootstrap-server localhost:9092 --topic test
   ```

3. **Read the message:**
   ```powershell
   docker exec kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic test --from-beginning --max-messages 1
   ```

4. **View in Control Center:**
   - Open http://localhost:9021
   - Go to Topics → test
   - Click on Messages to see your message

---

**Your Kafka cluster is ready to use! 🎉**







